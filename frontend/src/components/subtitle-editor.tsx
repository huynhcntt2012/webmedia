"use client";
import {useEffect,useState} from 'react';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';
type Track={language:string;label:string;content:string;version:number};
export function SubtitleEditor({jobId}:{jobId:string}){
 const [tracks,setTracks]=useState<Track[]>([]),[language,setLanguage]=useState('vi'),[label,setLabel]=useState('Tiếng Việt'),[content,setContent]=useState(''),[version,setVersion]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 async function read(){if(!await loadUser())throw new Error('Vui lòng đăng nhập.');const r=await fetch(`/api/admin/media-jobs/${jobId}/subtitles`,{cache:'no-store'});if(!r.ok)throw new Error(await errorMessage(r));return (await r.json()).items as Track[];}
 useEffect(()=>{let alive=true;void (async()=>{if(!await loadUser())return;const r=await fetch(`/api/admin/media-jobs/${jobId}/subtitles`,{cache:'no-store'});if(r.ok&&alive)setTracks((await r.json()).items);})().catch(()=>{});return()=>{alive=false;};},[jobId]);
 async function save(){setBusy(true);setError('');setNotice('');try{if(!await loadUser())throw new Error('Vui lòng đăng nhập.');const r=await csrfRequest(`admin/media-jobs/${jobId}/subtitles/${language}`,'PUT',{label,content,version});if(!r.ok)throw new Error(await errorMessage(r));const result=await r.json();setVersion(result.version);setTracks(await read());setNotice('Đã lưu phụ đề.');}catch(e){setError(e instanceof Error?e.message:'Không lưu được phụ đề.');}finally{setBusy(false);}}
 async function remove(t:Track){if(!confirm(`Xóa phụ đề ${t.label}?`))return;setBusy(true);try{if(!await loadUser())throw new Error('Vui lòng đăng nhập.');const r=await csrfRequest(`admin/media-jobs/${jobId}/subtitles/${t.language}?version=${t.version}`,'DELETE');if(!r.ok)throw new Error(await errorMessage(r));setTracks(await read());setVersion(0);setContent('');setNotice('Đã xóa phụ đề.');}catch(e){setError(e instanceof Error?e.message:'Không xóa được.');}finally{setBusy(false);}}
 return <section className="subtitle-editor"><h4>Phụ đề WebVTT</h4><p>Văn bản thuần, tối đa 128 KiB; thời gian cue nằm trong video.</p>{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  <ul>{tracks.map(t=><li key={t.language}>{t.label} <button disabled={busy} onClick={()=>{setLanguage(t.language);setLabel(t.label);setContent(t.content);setVersion(t.version);}}>Sửa phụ đề {t.language}</button> <button disabled={busy} onClick={()=>void remove(t)}>Xóa phụ đề {t.language}</button></li>)}</ul>
  <label>Mã ngôn ngữ<input value={language} maxLength={12} disabled={busy||version>0} onChange={e=>setLanguage(e.target.value)}/></label>
  <label>Tên phụ đề<input value={label} maxLength={80} disabled={busy} onChange={e=>setLabel(e.target.value)}/></label>
  <label>File phụ đề VTT<input type="file" accept=".vtt,text/vtt" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>131072){setError('File phụ đề vượt 128 KiB.');return;}setContent(await file.text());}}/></label>
  <label>Nội dung WebVTT<textarea value={content} disabled={busy} maxLength={131072} rows={6} onChange={e=>setContent(e.target.value)}/></label>
  <div className="admin-actions"><button disabled={busy||!content||!/^[a-z]{2,3}(?:-[A-Z]{2})?$/.test(language)} onClick={()=>void save()}>Lưu phụ đề</button><button disabled={busy} onClick={()=>{setVersion(0);setContent('');setLanguage('vi');setLabel('Tiếng Việt');}}>Phụ đề mới</button><button disabled={busy} onClick={()=>{void read().then(setTracks).catch(()=>setError('Không tải được phụ đề.'));}}>Tải lại phụ đề</button></div>
 </section>;
}
