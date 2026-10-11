"use client";
import {useState} from 'react';
export function Poster({url,title,detail=false}:{url:string|null;title:string;detail?:boolean}){
 const [failed,setFailed]=useState(false);
 return <div className={`poster-placeholder ${detail?'detail-poster':''}`} aria-hidden="true">
  {url&&!failed? /* Browser fetch only: bypass server image optimizer to avoid SSRF. */
   /* eslint-disable-next-line @next/next/no-img-element */
   <img ref={node=>{if(node?.complete && node.naturalWidth===0)setFailed(true);}} src={url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={()=>setFailed(true)}/>
   :<><span className="poster-mark">s.</span><span className="poster-title">{title}</span><span className="poster-note">{failed?'Không tải được poster':'Chưa có poster'}</span></>}
 </div>;
}
