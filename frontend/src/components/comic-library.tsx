'use client';
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {errorMessage} from '../lib/auth-client';
type Comic={title:string;slug:string;synopsis:string;required_plan_code:string};
type Chapter={id:string;title:string;chapter_number:number};
export function ComicLibrary({slug}:{slug?:string}){
 const [items,setItems]=useState<(Comic|Chapter)[]>([]),[comic,setComic]=useState<Comic|null>(null),[page,setPage]=useState(1),[total,setTotal]=useState(0),[q,setQ]=useState(''),[query,setQuery]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{const controller=new AbortController();
  void fetch(`/api/comics${slug?`/${encodeURIComponent(slug)}`:''}?page=${page}&q=${encodeURIComponent(query)}`,{cache:'no-store',signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error(await errorMessage(r));return r.json();}).then(d=>{setItems(d.items);setTotal(d.total);setComic(d.comic??null);}).catch(e=>{if(!controller.signal.aborted)setError(e.message);}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
 },[slug,page,query]);
 return <section className="comic-library"><Link href={slug?'/comics':'/'}>← {slug?'Thư viện truyện':'Trang chủ'}</Link><h1>{comic?.title??(slug?'Chi tiết truyện':'Truyện tranh')}</h1>{comic&&<p>{comic.synopsis}</p>}
 {!slug&&<form className="movie-search" onSubmit={e=>{e.preventDefault();if(page===1&&q===query)return;setLoading(true);setError('');setPage(1);setQuery(q);}}><label>Tìm tên truyện<input value={q} onChange={e=>setQ(e.target.value)} maxLength={100}/></label><button className="button">Tìm truyện</button></form>}
 {error?<p role="alert">{error} <button onClick={()=>window.location.reload()}>Thử lại</button></p>:loading?<p role="status">Đang tải truyện…</p>:<><ul className="comic-library-list">{items.map(item=>'slug' in item?<li key={item.slug}><Link href={`/comics/${item.slug}`}><h2>{item.title}</h2></Link><p>{item.required_plan_code.toUpperCase()}</p><p>{item.synopsis.slice(0,200)}</p></li>:<li key={item.id}><Link href={`/read/${item.id}`}>Chương {item.chapter_number}: {item.title}</Link></li>)}</ul>{!items.length&&<p role="status">{slug?'Chưa có chương.':'Chưa có truyện phù hợp.'}</p>}<nav aria-label="Phân trang truyện"><button disabled={page===1} onClick={()=>{setLoading(true);setError('');setPage(page-1);}}>Trước</button><span> Trang {page} </span><button disabled={page*20>=total||page>=1000} onClick={()=>{setLoading(true);setError('');setPage(page+1);}}>Sau</button></nav></>}
 </section>;
}
