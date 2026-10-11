"use client";
import {useEffect,useRef,useState} from 'react';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';
import {SubtitleEditor} from './subtitle-editor';

type Upload={id:string;filename:string;total_bytes:number;received_bytes:number;chunk_bytes:number;status:string;expires_at:string;chunks:{offset:number;size:number;sha256:string}[];job:null|{id:string;status:string;attempts:number;error_code:string|null;duration_seconds:number|null;variants:{profile:string;width:number;height:number}[]}};
async function readUpload(id:string):Promise<Upload>{if(!await loadUser())throw new Error('Đăng nhập lại để xem tiến độ.');const r=await fetch(`/api/admin/uploads/${id}`,{cache:'no-store'});if(!r.ok)throw new Error(await errorMessage(r));return r.json();}
async function hash(buffer:ArrayBuffer){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),b=>b.toString(16).padStart(2,'0')).join('');}
async function write(path:string,method:string,data?:unknown,checksum?:string){if(!await loadUser())throw new Error('Đăng nhập lại để tiếp tục upload.');const r=await csrfRequest(`admin/${path}`,method,data,checksum);if(!r.ok)throw new Error(await errorMessage(r));return r.json();}
const size=(n:number)=>`${(n/1024/1024).toFixed(1)} MB`;
const statuses:Record<string,string>={uploading:'Đang nhận file',sealed:'Đã nhận file',queued:'Đang chờ xử lý',processing:'Đang chuyển mã',ready:'Video sẵn sàng',failed:'Xử lý chưa thành công',cancelled:'Đã hủy',expired:'Đã hết hạn'};

export function VideoUpload({episodeId,title}:{episodeId:string;title:string}){
 const [current,setCurrent]=useState<Upload|null>(null),[file,setFile]=useState<File|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[maximum,setMaximum]=useState(1073741824);
 const pause=useRef(false),alive=useRef(true);
 const storageKey=`suni-upload-${episodeId}`;
 useEffect(()=>{alive.current=true;pause.current=false;(async()=>{try{
  const user=await loadUser();if(!user)throw new Error('Vui lòng đăng nhập.');
  const [history,settings]=await Promise.all([fetch(`/api/admin/episodes/${episodeId}/uploads`,{cache:'no-store'}),fetch('/api/admin/catalogue-settings',{cache:'no-store'})]);
  if(!history.ok)throw new Error(await errorMessage(history));
  const data=await history.json();const config=await settings.json();
  if(alive.current){setCurrent(data.items[0]??null);setMaximum(config.upload_max_bytes??1073741824);}
 }catch(e){if(alive.current)setError(e instanceof Error?e.message:'Không tải được phiên upload.');}})();return()=>{alive.current=false;pause.current=true;};},[episodeId]);
 useEffect(()=>{
  if(!current?.job||!['queued','processing'].includes(current.job.status))return;
  let disposed=false;
  const timer=setInterval(()=>{void readUpload(current.id).then(value=>{if(!disposed)setCurrent(value);}).catch(()=>{if(!disposed)setError('Chưa đọc được tiến độ. Tải lại để kiểm tra.');});},2000);
  return()=>{disposed=true;clearInterval(timer);};
 },[current?.id,current?.job]);
 async function start(){
  if(!file)return;
  setBusy(true);setError('');setMessage('Đang kiểm tra file…');pause.current=false;
  try{
   if(!file.name.toLowerCase().endsWith('.mp4')||(file.type&&file.type!=='video/mp4')||file.size>maximum||file.size===0)throw new Error(`Chọn MP4 không quá ${size(maximum)}.`);
   let upload=current?await readUpload(current.id):null;
   if(!upload){
    let key=crypto.randomUUID();
    try{const saved=JSON.parse(localStorage.getItem(storageKey)??'null');if(saved?.name===file.name&&saved?.size===file.size)key=saved.key;localStorage.setItem(storageKey,JSON.stringify({key,name:file.name,size:file.size}));}catch{/* Storage disabled: server history still supports resuming. */}
    upload=await write('uploads','POST',{episode_id:episodeId,idempotency_key:key,filename:file.name,total_bytes:file.size,content_type:'video/mp4'}) as Upload;
   }
   if(upload.status!=='uploading')throw new Error('Phiên này không nhận thêm dữ liệu. Chọn tạo upload mới.');
   if(upload.filename!==file.name||upload.total_bytes!==file.size)throw new Error('Chọn lại đúng file đã upload.');
   setCurrent(upload);setMessage('Đang xác minh phần đã gửi…');
   for(const part of upload.chunks){
    if(pause.current)break;
    if(await hash(await file.slice(part.offset,part.offset+part.size).arrayBuffer())!==part.sha256)throw new Error('File khác với phiên đang tiếp tục. Không trộn dữ liệu hai file.');
   }
   for(let offset=upload.received_bytes;offset<file.size&&!pause.current;offset+=upload.chunk_bytes){
    const bytes=await file.slice(offset,offset+upload.chunk_bytes).arrayBuffer();
    await write(`uploads/${upload.id}/chunks?offset=${offset}`,'PUT',bytes,await hash(bytes));
    if(alive.current){upload=await readUpload(upload.id);setCurrent(upload);setMessage('Đang gửi video…');}
   }
   if(pause.current){if(alive.current)setMessage('Đã tạm dừng. Chọn đúng file để tiếp tục.');return;}
   await write(`uploads/${upload.id}/complete`,'POST');
   if(alive.current){setCurrent(await readUpload(upload.id));setMessage('Đã gửi đủ video. Hệ thống đang chuẩn bị HLS và thumbnail.');}
  }catch(e){if(alive.current)setError(e instanceof Error?e.message:'Upload gián đoạn. Chọn tiếp tục để thử lại.');}
  finally{if(alive.current)setBusy(false);}
 }
 async function action(kind:'retry'|'cancel'){
  if(!current)return;if(kind==='cancel'&&!window.confirm('Hủy phiên upload và dọn file đã gửi?'))return;
  setBusy(true);setError('');try{await write(`uploads/${current.id}${kind==='retry'?'/retry':''}`,kind==='retry'?'POST':'DELETE');setCurrent(await readUpload(current.id));}catch(e){setError(e instanceof Error?e.message:'Không thực hiện được.');}finally{setBusy(false);}
 }
 const status=current?.job?.status??current?.status;
 return <section className="video-upload" aria-label={`Video của ${title}`}><h3>Video · {title}</h3>
  <p>MP4 (H.264/H.265), tối đa {size(maximum)}, 60 phút. Có thể tạm dừng rồi chọn lại đúng file để tiếp tục trong 24 giờ.</p>
  {error&&<p className="admin-error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
  {current&&<><p className="upload-status" role="status">{statuses[status??'']??status}</p><p>{current.filename} · {size(current.received_bytes)} / {size(current.total_bytes)}</p><progress aria-label="Tiến độ upload" value={current.received_bytes} max={current.total_bytes}/>
   {current.job?.error_code&&<p>Mã lỗi: {current.job.error_code}. Kiểm tra file nguồn hoặc thử lại (tối đa 3 lần xử lý).</p>}
   {current.job?.status==='ready'&&<><p>HLS: {current.job.variants.map(v=>`${v.width}×${v.height}`).join(' · ')} · {current.job.duration_seconds} giây</p>
    {/* Authenticated image endpoint must bypass the image optimizer. */}
    {/* eslint-disable-next-line @next/next/no-img-element */}
    <img className="video-thumbnail" src={`/api/admin/media-jobs/${current.job.id}/thumbnail`} alt={`Thumbnail ${title}`} referrerPolicy="no-referrer"/><p>Video đã xử lý. Xuất bản phim để người có quyền xem có thể phát video.</p><SubtitleEditor key={current.job.id} jobId={current.job.id}/></>}
  </>}
  {(!current||current.status==='uploading')&&<><label>File video MP4<input type="file" accept="video/mp4,.mp4" disabled={busy} onChange={e=>setFile(e.target.files?.[0]??null)}/></label><div className="admin-actions"><button type="button" disabled={busy||!file} onClick={()=>void start()}>{current?'Tiếp tục upload':'Bắt đầu upload'}</button>{busy&&<button type="button" onClick={()=>{pause.current=true;}}>Tạm dừng</button>}</div></>}
  {current&&<div className="admin-actions">{current.job?.status==='failed'&&current.job.attempts<3&&<button disabled={busy} onClick={()=>void action('retry')}>Thử xử lý lại</button>}
   {current.job?.status!=='ready'&&!['cancelled','expired'].includes(current.status)&&<button disabled={busy} className="danger" onClick={()=>void action('cancel')}>Hủy upload</button>}
   {(['ready','failed','cancelled'].includes(current.job?.status??'')||['cancelled','expired'].includes(current.status))&&<button disabled={busy} onClick={()=>{setCurrent(null);setFile(null);setError('');setMessage('');try{localStorage.removeItem(storageKey);}catch{}}}>Tạo upload mới</button>}
  </div>}
 </section>;
}
