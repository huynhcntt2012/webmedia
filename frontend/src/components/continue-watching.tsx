"use client";
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {loadUser} from '../lib/auth-client';
type Item={episode_id:string;title:string;movie_title:string;position_ms:number};
export function ContinueWatching(){
 const [items,setItems]=useState<Item[]>([]);
 useEffect(()=>{let alive=true;void (async()=>{if(!await loadUser())return;const r=await fetch('/api/playback/continue',{cache:'no-store'});if(r.ok&&alive)setItems((await r.json()).items);})().catch(()=>{});return()=>{alive=false;};},[]);
 if(!items.length)return null;
 return <section className="catalogue-section"><h2>Tiếp tục xem</h2><ul className="episode-list">{items.map(item=><li key={item.episode_id}><Link href={`/watch/${item.episode_id}`}>{item.movie_title} · {item.title}<small>Tiếp tục từ {Math.floor(item.position_ms/1000)} giây →</small></Link></li>)}</ul></section>;
}
