"use client";
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';
type Comic={id?:string;title:string;slug:string;synopsis:string;status:string;required_plan_code:string;version?:number};
type Chapter={id?:string;title:string;chapter_number:number;version?:number};
type Page={id:string;page_number:number;width:number;height:number};
type List<T>={items:T[];total:number;page:number;page_size:number};
type Pending={file:File;key:string;state:'pending'|'done'|'error';message:string};
const emptyComic:Comic={title:'',slug:'',synopsis:'',status:'draft',required_plan_code:'free'};
const emptyChapter:Chapter={title:'',chapter_number:1};
async function api(path:string,method='GET',data?:unknown,hash?:string){
 if(!await loadUser())throw new Error('Vui lòng đăng nhập.');
 const r=method==='GET'?await fetch(`/api/admin/comics${path}`,{cache:'no-store'}):await csrfRequest(`admin/comics${path}`,method,data,hash);
 if(!r.ok)throw new Error(await errorMessage(r));return r.status===204?null:r.json();
}
export function AdminComics(){
 const [authorized,setAuthorized]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[query,setQuery]=useState('');
 const [list,setList]=useState<List<Comic>>({items:[],total:0,page:1,page_size:20}),[comic,setComic]=useState<Comic|null>(null),[chapters,setChapters]=useState<List<Chapter>>({items:[],total:0,page:1,page_size:20}),[chapter,setChapter]=useState<Chapter|null>(null),[pages,setPages]=useState<Page[]>([]),[queue,setQueue]=useState<Pending[]>([]);
 const pause=useRef(false),alive=useRef(true);
 useEffect(()=>{alive.current=true;void (async()=>{const user=await loadUser();if(!user||user.role!=='admin')throw new Error('Trang này yêu cầu tài khoản Admin.');const rows=await api('');if(alive.current){setAuthorized(true);setList(rows);}})().catch(e=>{if(alive.current)setError(e.message);});return()=>{alive.current=false;pause.current=true;};},[]);
 async function perform(action:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await action();}catch(e){setError(e instanceof Error?e.message:'Thao tác chưa thành công.');}finally{setBusy(false);}}
 async function reloadList(page=1){setList(await api(`?q=${encodeURIComponent(query)}&page=${page}`));}
 async function openComic(id:string){await perform(async()=>{setComic(await api(`/${id}`));setChapters(await api(`/${id}/chapters`));setChapter(null);setPages([]);setQueue([]);});}
 async function openChapter(row:Chapter){await perform(async()=>{const result=await api(`/${comic!.id}/chapters/${row.id}/pages`);setChapter(result.chapter);setPages(result.items);setQueue([]);});}
 async function refreshPages(){const result=await api(`/${comic!.id}/chapters/${chapter!.id}/pages`);setChapter(result.chapter);setPages(result.items);return result;}
 async function saveComic(){if(!comic)return;await perform(async()=>{const {id,...data}=comic;setComic(await api(id?`/${id}`:'',id?'PUT':'POST',data));await reloadList();setNotice('Đã lưu truyện.');});}
 async function saveChapter(){if(!chapter||!comic?.id)return;await perform(async()=>{const {id,version,title,chapter_number}=chapter;const data={title,chapter_number,...(id?{version}:{})};setChapter(await api(`/${comic.id}/chapters${id?`/${id}`:''}`,id?'PUT':'POST',data));setChapters(await api(`/${comic.id}/chapters?page=${chapters.page}`));setNotice('Đã lưu chương.');});}
 async function removeComic(){if(!comic?.id||!confirm('Xóa truyện, toàn bộ chương và ảnh?'))return;await perform(async()=>{await api(`/${comic.id}?version=${comic.version}`,'DELETE');setComic(null);setChapter(null);setPages([]);setQueue([]);await reloadList();setNotice('Đã xóa truyện và ảnh liên quan.');});}
 async function removeChapter(){if(!chapter?.id||!confirm('Xóa chương và toàn bộ ảnh?'))return;await perform(async()=>{await api(`/${comic!.id}/chapters/${chapter.id}?version=${chapter.version}`,'DELETE');setChapter(null);setPages([]);setQueue([]);setChapters(await api(`/${comic!.id}/chapters`));setNotice('Đã xóa chương.');});}
 async function move(index:number,delta:number){await perform(async()=>{const ordered=[...pages];[ordered[index],ordered[index+delta]]=[ordered[index+delta],ordered[index]];const result=await api(`/${comic!.id}/chapters/${chapter!.id}/pages/order`,'PUT',{version:chapter!.version,page_ids:ordered.map(p=>p.id)});setChapter(result.chapter);setPages(result.items);setNotice('Đã lưu thứ tự trang.');});}
 async function removePage(row:Page){if(!confirm(`Xóa trang ${row.page_number}?`))return;await perform(async()=>{await api(`/${comic!.id}/chapters/${chapter!.id}/pages/${row.id}?version=${chapter!.version}`,'DELETE');await refreshPages();setNotice('Đã xóa trang.');});}
 async function upload(){
  if(!comic?.id||!chapter?.id)return;setBusy(true);setError('');setNotice('');pause.current=false;
  const next=queue.map(item=>({...item}));let current=chapter;
  try{
   const fresh=await refreshPages();current=fresh.chapter;
   for(let i=0;i<next.length&&!pause.current;i++){
    const item=next[i];if(item.state==='done')continue;
    try{
     if(!/\.(png|jpe?g|webp)$/i.test(item.file.name)||item.file.size>8*1024*1024||!item.file.size)throw new Error('Chọn JPEG/PNG/WebP tối đa 8 MiB.');
     const bytes=await item.file.arrayBuffer();const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
     const result=await api(`/${comic.id}/chapters/${current.id}/pages?upload_key=${item.key}&version=${current.version}`,'POST',bytes,hash);
     current=result.chapter;item.state='done';item.message='Đã lưu';
    }catch(e){item.state='error';item.message=e instanceof Error?e.message:'Không tải được ảnh.';}
    if(alive.current)setQueue(next.map(q=>({...q})));
   }
   if(alive.current){await refreshPages();setNotice(pause.current?'Đã dừng sau ảnh hiện tại.':'Đã xử lý danh sách ảnh. Có thể thử lại riêng các ảnh lỗi.');}
  }catch(e){if(alive.current)setError(e instanceof Error?e.message:'Không tải được ảnh.');}
  finally{if(alive.current)setBusy(false);}
 }
 return <main className="admin-shell"><header className="admin-header"><Link className="brand" href="/">suni<span>STUDIO</span></Link><Link href="/admin">Quản lý phim →</Link></header><p className="eyebrow">QUẢN TRỊ NỘI DUNG</p><h1>Truyện tranh</h1>
  {error&&<div role="alert" className="admin-error">{error}<button disabled={busy} onClick={()=>window.location.reload()}>Tải lại dữ liệu</button></div>}{notice&&<p role="status" className="admin-notice">{notice}</p>}
  {!authorized&&!error&&<p>Đang kiểm tra quyền quản trị…</p>}
  {authorized&&<><div className={`admin-columns ${comic?'has-editor':''}`}><section className="admin-panel"><div className="section-heading"><h2>Danh sách truyện</h2><button disabled={busy} onClick={()=>{setComic({...emptyComic});setChapter(null);setPages([]);setQueue([]);setChapters({items:[],total:0,page:1,page_size:20});}}>Tạo truyện</button></div>
   <form className="admin-filter" onSubmit={e=>{e.preventDefault();void perform(()=>reloadList());}}><label>Tìm truyện<input maxLength={100} value={query} onChange={e=>setQuery(e.target.value)}/></label><button disabled={busy}>Lọc truyện</button></form>
   <ul className="admin-records">{list.items.map(row=><li key={row.id}><div><strong>{row.title}</strong><small>{row.status} · {row.required_plan_code.toUpperCase()}</small></div><button disabled={busy} onClick={()=>void openComic(row.id!)}>Sửa truyện {row.title}</button></li>)}</ul>
   <div className="admin-actions"><button disabled={busy||list.page===1} onClick={()=>void perform(()=>reloadList(list.page-1))}>Truyện trước</button><span>Trang {list.page} · {list.total} truyện</span><button disabled={busy||list.page*20>=list.total} onClick={()=>void perform(()=>reloadList(list.page+1))}>Truyện sau</button></div>
  </section>{comic&&<section className="admin-panel comic-editor"><h2>{comic.id?'Chỉnh sửa truyện':'Truyện mới'}</h2><form className="admin-form" onSubmit={e=>{e.preventDefault();void saveComic();}}><fieldset disabled={busy}>
   <label>Tên truyện<input required maxLength={200} value={comic.title} onChange={e=>setComic({...comic,title:e.target.value})}/></label><label>Slug truyện<input required maxLength={200} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={comic.slug} onChange={e=>setComic({...comic,slug:e.target.value})}/></label>
   <label>Mô tả truyện<textarea maxLength={5000} rows={4} value={comic.synopsis} onChange={e=>setComic({...comic,synopsis:e.target.value})}/></label>
   <label>Trạng thái truyện<select aria-label="Trạng thái truyện" value={comic.status} onChange={e=>setComic({...comic,status:e.target.value})}><option value="draft">Nháp</option><option value="published">Xuất bản</option><option value="archived">Lưu trữ</option></select></label>
   <label>Gói truyện<select aria-label="Gói truyện" value={comic.required_plan_code} onChange={e=>setComic({...comic,required_plan_code:e.target.value})}><option value="free">Free</option><option value="vip">VIP</option><option value="premium">Premium</option></select></label><button>Lưu truyện</button></fieldset></form>
   {comic.id&&<><button disabled={busy} className="danger" onClick={()=>void removeComic()}>Xóa truyện</button><h2>Các chương</h2><button disabled={busy} onClick={()=>{setChapter({...emptyChapter});setPages([]);setQueue([]);}}>Thêm chương</button>
    <ul className="admin-records">{chapters.items.map(row=><li key={row.id}><span>Chương {row.chapter_number}: {row.title}</span><button disabled={busy} onClick={()=>void openChapter(row)}>Mở chương {row.title}</button></li>)}</ul>
    <div className="admin-actions"><button disabled={busy||chapters.page===1} onClick={()=>void perform(async()=>setChapters(await api(`/${comic.id}/chapters?page=${chapters.page-1}`)))}>Chương trước</button><span>Trang {chapters.page}</span><button disabled={busy||chapters.page*20>=chapters.total} onClick={()=>void perform(async()=>setChapters(await api(`/${comic.id}/chapters?page=${chapters.page+1}`)))}>Chương sau</button></div>
   </>}
  </section>}</div>
  {comic?.id&&chapter&&<section className="admin-panel chapter-editor"><h2>{chapter.id?'Biên tập chương':'Chương mới'}</h2><form className="admin-form" onSubmit={e=>{e.preventDefault();void saveChapter();}}><fieldset disabled={busy}><label>Tên chương<input required maxLength={200} value={chapter.title} onChange={e=>setChapter({...chapter,title:e.target.value})}/></label><label>Số chương<input required type="number" min={1} max={100000} value={chapter.chapter_number} onChange={e=>setChapter({...chapter,chapter_number:Number(e.target.value)})}/></label><button>Lưu chương</button></fieldset></form>
   {chapter.id&&<><div className="admin-actions"><button disabled={busy} className="danger" onClick={()=>void removeChapter()}>Xóa chương</button><button disabled={busy} onClick={()=>void perform(async()=>{await refreshPages();})}>Tải lại trang chương</button></div>
    <h3>Ảnh trong chương</h3><p>JPEG/PNG/WebP tĩnh, tối đa 8 MiB và 12 triệu pixel/ảnh. Tối đa 500 trang/chương. Các ảnh được thêm theo thứ tự danh sách.</p>
    <label>Chọn nhiều ảnh<input type="file" multiple accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" disabled={busy} onChange={e=>{const files=Array.from(e.target.files??[]);if(files.length>50){setError('Mỗi lần chọn tối đa 50 ảnh.');return;}setQueue(files.map(file=>({file,key:crypto.randomUUID(),state:'pending',message:''})));}}/></label>
    {queue.length>0&&<><ol className="upload-results">{queue.map(item=><li key={item.key}>{item.file.name} — {item.message||'Chờ upload'}</li>)}</ol><button disabled={busy||queue.every(q=>q.state==='done')} onClick={()=>void upload()}>Tải ảnh / thử lại ảnh lỗi</button>{busy&&<button onClick={()=>{pause.current=true;}}>Dừng sau ảnh hiện tại</button>}</>}
    <ol className="comic-page-grid">{pages.map((row,index)=><li key={row.id} data-page-id={row.id}><p>Trang {row.page_number} · {row.width}×{row.height}</p>
     {/* Private Admin route must bypass Next image optimizer. */}
     {/* eslint-disable-next-line @next/next/no-img-element */}
     <img src={`/api/admin/comics/${comic.id}/chapters/${chapter.id}/pages/${row.id}/image`} alt={`Trang ${row.page_number}`} loading="lazy"/>
     <div className="admin-actions"><button disabled={busy||index===0} onClick={()=>void move(index,-1)}>Đưa trang {row.page_number} lên</button><button disabled={busy||index===pages.length-1} onClick={()=>void move(index,1)}>Đưa trang {row.page_number} xuống</button><button disabled={busy} className="danger" onClick={()=>void removePage(row)}>Xóa trang {row.page_number}</button></div></li>)}</ol>
   </>}
  </section>}
  </>}
 </main>;
}
