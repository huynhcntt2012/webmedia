"use client";
import {FormEvent,useEffect,useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {VideoUpload} from './video-upload';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';

type Genre={id:string;name:string;slug:string;version:number};
type Film={id:string;title:string;slug:string;synopsis:string;release_year:number|null;status:string;required_plan_code:string;poster_url:string|null;trailer_url:string|null;genres:Genre[];version:number};
type Episode={id:string;movie_id:string;title:string;season_number:number;episode_number:number;duration_seconds:number|null;version:number};
type Audit={id:string;actor_id:string|null;action:string;entity_type:string;entity_id:string;changed_fields:string[];created_at:string};
type Page<T>={items:T[];total:number;page:number};
const empty=<T,>():Page<T>=>({items:[],total:0,page:1});
const blankFilm:Film={id:'',title:'',slug:'',synopsis:'',release_year:null,status:'draft',required_plan_code:'free',poster_url:null,trailer_url:null,genres:[],version:1};
const blankGenre:Genre={id:'',name:'',slug:'',version:1};
const blankEpisode:Episode={id:'',movie_id:'',title:'',season_number:1,episode_number:1,duration_seconds:null,version:1};

async function api<T>(path:string,method='GET',data?:unknown):Promise<T>{
 if(method!=='GET' && !await loadUser())throw new Error('Phiên đã hết hạn. Đăng nhập lại trước khi lưu.');
 const response=method==='GET'?await fetch(`/api/admin/${path}`,{cache:'no-store'}):await csrfRequest(`admin/${path}`,method,data);
 if(!response.ok)throw new Error(await errorMessage(response));
 return response.status===204?undefined as T:await response.json();
}
function Pager({page,total,size,change,disabled}:{page:number;total:number;size:number;change:(p:number)=>void;disabled:boolean}){
 return <div className="admin-pager"><button type="button" disabled={disabled||page<=1} onClick={()=>change(page-1)}>Trước</button><span>Trang {page} · {total} bản ghi</span><button type="button" disabled={disabled||page*size>=total||page>=1000} onClick={()=>change(page+1)}>Sau</button></div>;
}

export function AdminCatalogue(){
 const router=useRouter();
 const [authorized,setAuthorized]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [films,setFilms]=useState(empty<Film>),[genres,setGenres]=useState(empty<Genre>),[episodes,setEpisodes]=useState(empty<Episode>),[audit,setAudit]=useState(empty<Audit>);
 const [film,setFilm]=useState<Film|null>(null),[genre,setGenre]=useState(blankGenre),[episode,setEpisode]=useState(blankEpisode);
 const [query,setQuery]=useState(''),[status,setStatus]=useState(''),[hosts,setHosts]=useState<string[]>([]);
 const [uploadEpisode,setUploadEpisode]=useState<Episode|null>(null);
 const [tab,setTab]=useState<'movies'|'genres'|'audit'>('movies');
 const filmPath=(page=1)=>`movies?${new URLSearchParams({page:String(page),q:query,...(status?{status}:{})})}`;
 async function perform(action:()=>Promise<void>){
  setBusy(true);setError('');setNotice('');
  try{await action();}catch(e){setError(e instanceof Error?e.message:'Yêu cầu thất bại. Vui lòng thử lại.');}finally{setBusy(false);}
 }
 useEffect(()=>{
  let active=true;
  (async()=>{
   try{
    const user=await loadUser();if(!active)return;if(!user){router.replace('/login');return;}
    await api('check');
    const [f,g,s]=await Promise.all([api<Page<Film>>('movies'),api<Page<Genre>>('genres'),api<{poster_allowed_hosts:string[]}>('catalogue-settings')]);
    if(active){setFilms(f);setGenres(g);setHosts(s.poster_allowed_hosts);setAuthorized(true);}
   }catch(e){if(active)setError(e instanceof Error?e.message:'Không tải được khu vực quản trị.');}
  })();return()=>{active=false;};
 },[router]);
 async function openFilm(row:Film){
  setUploadEpisode(null);
  await perform(async()=>{const [fresh,eps]=await Promise.all([api<Film>(`movies/${row.id}`),api<Page<Episode>>(`movies/${row.id}/episodes`)]);setFilm(fresh);setEpisodes(eps);setEpisode(blankEpisode);});
 }
 async function saveFilm(event:FormEvent){
  event.preventDefault();if(!film)return;
  await perform(async()=>{
   const {id,genres:assigned,version,...values}=film;
   const saved=await api<Film>(id?`movies/${id}`:'movies',id?'PUT':'POST',{...values,genre_ids:assigned.map(g=>g.id),...(id?{version}:{})});
   setFilm(saved);setFilms(await api<Page<Film>>(filmPath()));setNotice('Đã lưu phim.');
  });
 }
 async function removeFilm(){
  if(!film?.id||!window.confirm(`Xóa phim “${film.title}” và toàn bộ tập? Thao tác này không thể hoàn tác.`))return;
  await perform(async()=>{await api(`movies/${film.id}?version=${film.version}`,'DELETE');setFilm(null);setEpisodes(empty());setFilms(await api<Page<Film>>(filmPath()));setNotice('Đã xóa phim và các tập.');});
 }
 async function saveGenre(event:FormEvent){
  event.preventDefault();await perform(async()=>{
   await api(genre.id?`genres/${genre.id}`:'genres',genre.id?'PUT':'POST',{name:genre.name,slug:genre.slug,...(genre.id?{version:genre.version}:{})});
   setGenre(blankGenre);setGenres(await api<Page<Genre>>(`genres?page=${genres.page}`));setNotice('Đã lưu thể loại.');
  });
 }
 async function removeGenre(row:Genre){
  if(!window.confirm(`Xóa thể loại “${row.name}”?`))return;
  await perform(async()=>{await api(`genres/${row.id}?version=${row.version}`,'DELETE');setGenres(await api<Page<Genre>>(`genres?page=${genres.page}`));setGenre(blankGenre);setNotice('Đã xóa thể loại.');});
 }
 async function saveEpisode(event:FormEvent){
  event.preventDefault();if(!film?.id)return;
  await perform(async()=>{
   const {id,version,title,season_number,episode_number,duration_seconds}=episode;
   await api(`movies/${film.id}/episodes${id?`/${id}`:''}`,id?'PUT':'POST',{title,season_number,episode_number,duration_seconds,...(id?{version}:{})});
   setEpisode(blankEpisode);setEpisodes(await api<Page<Episode>>(`movies/${film.id}/episodes?page=${episodes.page}`));setNotice('Đã lưu tập phim.');
  });
 }
 async function removeEpisode(row:Episode){
  if(!film?.id||!window.confirm(`Xóa tập “${row.title}”?`))return;
  await perform(async()=>{await api(`movies/${film.id}/episodes/${row.id}?version=${row.version}`,'DELETE');setEpisodes(await api<Page<Episode>>(`movies/${film.id}/episodes?page=${episodes.page}`));setEpisode(blankEpisode);setUploadEpisode(null);setNotice('Đã xóa tập.');});
 }
 function updateFilm(key:keyof Film,value:unknown){if(film)setFilm({...film,[key]:value});}
 return <main className="admin-shell">
  <header className="admin-header"><Link className="brand" href="/">suni<span>STUDIO</span></Link><Link href="/account">Tài khoản →</Link></header>
  <p className="eyebrow">QUẢN TRỊ NỘI DUNG</p><h1>Không gian biên tập</h1>
  {error&&<div className="admin-error" role="alert"><p>{error}</p><button type="button" onClick={()=>window.location.reload()}>Tải lại dữ liệu</button></div>}
  {notice&&<p className="admin-notice" role="status">{notice}</p>}
  {!authorized&&!error&&<p role="status">Đang kiểm tra quyền quản trị…</p>}
  {authorized&&<>
   <nav className="admin-tabs" aria-label="Quản lý nội dung">
    <Link href="/admin/comics">Truyện tranh</Link>
    <button disabled={busy} aria-current={tab==='movies'?'page':undefined} onClick={()=>setTab('movies')}>Phim & tập</button>
    <button disabled={busy} aria-current={tab==='genres'?'page':undefined} onClick={()=>setTab('genres')}>Thể loại</button>
    <button disabled={busy} aria-current={tab==='audit'?'page':undefined} onClick={()=>{setTab('audit');void perform(async()=>setAudit(await api<Page<Audit>>('audit-events')));}}>Nhật ký</button>
   </nav>
   {tab==='movies'&&<div className={`admin-columns ${film?"has-editor":""}`}>
    <section className="admin-panel"><div className="admin-section-heading"><h2>Danh sách phim</h2><button disabled={busy} onClick={()=>{setFilm({...blankFilm});setEpisodes(empty());setEpisode(blankEpisode);setNotice('');}}>+ Tạo phim</button></div>
     <form onSubmit={e=>{e.preventDefault();void perform(async()=>setFilms(await api<Page<Film>>(filmPath())));}} className="admin-filter">
      <label>Tìm phim<input value={query} maxLength={100} onChange={e=>setQuery(e.target.value)}/></label>
      <label>Trạng thái lọc<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Tất cả</option><option value="draft">Nháp</option><option value="published">Đã xuất bản</option><option value="archived">Lưu trữ</option></select></label><button disabled={busy}>Lọc</button>
     </form>
     {!films.items.length&&<p>Chưa có phim phù hợp.</p>}
     <ul className="admin-records">{films.items.map(row=><li key={row.id}><div><strong>{row.title}</strong><small>{row.status} · {row.required_plan_code.toUpperCase()}</small></div><button disabled={busy} onClick={()=>void openFilm(row)}>Sửa <span className="sr-only">{row.title}</span></button></li>)}</ul>
     <Pager {...films} size={20} disabled={busy} change={p=>void perform(async()=>setFilms(await api<Page<Film>>(filmPath(p))))}/>
    </section>
    <section className="admin-panel">{!film?<div className="admin-empty"><h2>Chọn câu chuyện để chỉnh sửa</h2><p>Tạo phim nháp, thêm thông tin và tập, rồi xuất bản khi sẵn sàng.</p></div>:<>
     <div className="admin-section-heading"><h2>{film.id?'Chỉnh sửa phim':'Tạo phim mới'}</h2><button disabled={busy} onClick={()=>setFilm(null)}>Đóng</button></div>
     <form className="admin-form" onSubmit={saveFilm}><fieldset disabled={busy}>
      <label>Tên phim<input required maxLength={200} value={film.title} onChange={e=>updateFilm('title',e.target.value)}/></label>
      <label>Slug phim<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" maxLength={200} value={film.slug} onChange={e=>updateFilm('slug',e.target.value)}/><small>Chữ thường không dấu, số và dấu gạch nối.</small></label>
      <label>Nội dung phim<textarea maxLength={5000} rows={5} value={film.synopsis} onChange={e=>updateFilm('synopsis',e.target.value)}/></label>
      <div className="admin-row"><label>Năm phát hành<input type="number" min={1888} max={9999} value={film.release_year??''} onChange={e=>updateFilm('release_year',e.target.value?Number(e.target.value):null)}/></label><label>Gói yêu cầu<select value={film.required_plan_code} onChange={e=>updateFilm('required_plan_code',e.target.value)}><option value="free">Free</option><option value="vip">VIP</option><option value="premium">Premium</option></select></label></div>
      <label>Trạng thái phim<select value={film.status} onChange={e=>updateFilm('status',e.target.value)}><option value="draft">Nháp</option><option value="published">Đã xuất bản</option><option value="archived">Lưu trữ</option></select></label>
      <label>URL poster<input type="url" maxLength={2048} value={film.poster_url??''} onChange={e=>updateFilm('poster_url',e.target.value||null)} placeholder="https://media.sunifactory.com/posters/phim.webp"/><small>HTTPS · {hosts.join(', ')||'Chưa cấu hình hostname'} · jpg/png/webp/avif, không query.</small></label>
      <label>URL trailer YouTube<input type="url" maxLength={500} value={film.trailer_url??''} onChange={e=>updateFilm('trailer_url',e.target.value||null)} placeholder="https://www.youtube.com/watch?v=…"/></label>
      <fieldset className="genre-checkboxes"><legend>Thể loại phim (tối đa 20)</legend>{genres.items.map(g=><label key={g.id}><input type="checkbox" checked={film.genres.some(x=>x.id===g.id)} onChange={e=>updateFilm('genres',e.target.checked?[...film.genres,g]:film.genres.filter(x=>x.id!==g.id))}/>{g.name}</label>)}{!genres.items.length&&<small>Tạo thể loại ở tab Thể loại trước.</small>}<small>Đã chọn: {film.genres.map(g=>g.name).join(', ')||'Chưa chọn'}</small></fieldset>
      {genres.total>100&&<Pager {...genres} size={100} disabled={busy} change={p=>void perform(async()=>setGenres(await api<Page<Genre>>(`genres?page=${p}`)))}/>}
      <button className="button" type="submit">{busy?'Đang lưu…':'Lưu phim'}</button>
     </fieldset></form>
     {film.id&&<><div className="admin-actions"><button className="danger" disabled={busy} onClick={()=>void removeFilm()}>Xóa phim</button><button disabled={busy} onClick={()=>void openFilm(film)}>Tải lại phim</button>{film.status==='published'&&<Link href={`/movies/${film.slug}`} target="_blank">Xem trang phim ↗</Link>}</div>
      <section className="episode-panel"><h2>Các tập phim</h2><ul className="admin-records">{episodes.items.map(row=><li key={row.id}><div><strong>{row.title}</strong><small>Mùa {row.season_number} · Tập {row.episode_number}</small></div><button disabled={busy} onClick={()=>setUploadEpisode(row)}>Video <span className="sr-only">{row.title}</span></button><button disabled={busy} onClick={()=>setEpisode(row)}>Sửa tập <span className="sr-only">{row.title}</span></button><button disabled={busy} className="danger" onClick={()=>void removeEpisode(row)}>Xóa tập <span className="sr-only">{row.title}</span></button></li>)}</ul>
       <Pager {...episodes} size={50} disabled={busy} change={p=>void perform(async()=>setEpisodes(await api<Page<Episode>>(`movies/${film.id}/episodes?page=${p}`)))}/>
       <>{uploadEpisode&&<VideoUpload key={uploadEpisode.id} episodeId={uploadEpisode.id} title={uploadEpisode.title}/>}</><h3>{episode.id?'Chỉnh sửa tập':'Thêm tập'}</h3><form className="admin-form" onSubmit={saveEpisode}><fieldset disabled={busy}>
        <label>Tên tập<input required maxLength={200} value={episode.title} onChange={e=>setEpisode({...episode,title:e.target.value})}/></label><div className="admin-row"><label>Mùa<input type="number" required min={1} max={10000} value={episode.season_number} onChange={e=>setEpisode({...episode,season_number:Number(e.target.value)})}/></label><label>Số tập<input type="number" required min={1} max={100000} value={episode.episode_number} onChange={e=>setEpisode({...episode,episode_number:Number(e.target.value)})}/></label></div><label>Thời lượng (giây)<input type="number" min={1} max={604800} value={episode.duration_seconds??''} onChange={e=>setEpisode({...episode,duration_seconds:e.target.value?Number(e.target.value):null})}/></label><div className="admin-actions"><button className="button">Lưu tập</button><button type="button" onClick={()=>setEpisode(blankEpisode)}>Nhập tập mới</button></div>
       </fieldset></form>
      </section></>}
    </>}</section>
   </div>}
   {tab==='genres'&&<section className="admin-panel"><h2>Quản lý thể loại</h2><form className="admin-form" onSubmit={saveGenre}><fieldset disabled={busy}><div className="admin-row"><label>Tên thể loại<input required maxLength={80} value={genre.name} onChange={e=>setGenre({...genre,name:e.target.value})}/></label><label>Slug thể loại<input required maxLength={80} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={genre.slug} onChange={e=>setGenre({...genre,slug:e.target.value})}/></label></div><div className="admin-actions"><button className="button">Lưu thể loại</button><button type="button" onClick={()=>setGenre(blankGenre)}>Nhập thể loại mới</button></div></fieldset></form><ul className="admin-records">{genres.items.map(g=><li key={g.id}><div><strong>{g.name}</strong><small>{g.slug}</small></div><button disabled={busy} onClick={()=>setGenre(g)}>Sửa thể loại <span className="sr-only">{g.name}</span></button><button disabled={busy} className="danger" onClick={()=>void removeGenre(g)}>Xóa thể loại <span className="sr-only">{g.name}</span></button></li>)}</ul><Pager {...genres} size={100} disabled={busy} change={p=>void perform(async()=>setGenres(await api<Page<Genre>>(`genres?page=${p}`)))}/></section>}
   {tab==='audit'&&<section className="admin-panel"><h2>Nhật ký thay đổi</h2><p>Ghi nhận tài khoản, bản ghi và các trường được thay đổi.</p><ol className="audit-list">{audit.items.map(row=><li key={row.id}><strong>{row.action} · {row.entity_type}</strong><time>{new Date(row.created_at).toLocaleString('vi-VN')}</time><p>Bản ghi: {row.entity_id}</p><p>Tài khoản: {row.actor_id??'Đã xóa'}</p><small>{row.changed_fields.join(', ')||'Xóa bản ghi'}</small></li>)}</ol><Pager {...audit} size={50} disabled={busy} change={p=>void perform(async()=>setAudit(await api<Page<Audit>>(`audit-events?page=${p}`)))}/></section>}
  </>}
 </main>;
}
