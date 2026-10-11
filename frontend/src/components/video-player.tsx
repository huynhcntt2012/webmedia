"use client";
import Hls from 'hls.js';
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';

type Playback={episode_id:string;job_id:string;title:string;movie_title:string;movie_slug:string;duration_ms:number;variants:{profile:string;height:number}[];subtitles:{language:string;label:string}[];progress:{position_ms:number;completed:boolean;version:number}};
export function VideoPlayer({episodeId}:{episodeId:string}){
 const video=useRef<HTMLVideoElement>(null),engine=useRef<Hls|null>(null);
 const [info,setInfo]=useState<Playback|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[retry,setRetry]=useState(0),[quality,setQuality]=useState('-1'),[subtitle,setSubtitle]=useState(''),[playing,setPlaying]=useState(false);
 useEffect(()=>{
  const media=video.current!;let disposed=false,hls:Hls|null=null,timer:ReturnType<typeof setInterval>|undefined,authTimer:ReturnType<typeof setInterval>|undefined;
  let initialized=false,touched=false,inflight=false,pending=false,blocked=false,lastPosition=-1,version=0,config:Playback,recoveries=0;
  const handlers: [string,EventListener][]=[];
  function listen(name:string,handler:EventListener){handlers.push([name,handler]);media.addEventListener(name,handler);}
  async function save(){
   if(disposed||!initialized||!touched||blocked||media.seeking)return;
   if(inflight){pending=true;setNotice('Đang lưu tiến độ…');return;}
   const position=media.ended?config.duration_ms:Math.min(config.duration_ms,Math.max(0,Math.round(media.currentTime*1000)));
   if(position===lastPosition){setNotice('Đã lưu tiến độ xem.');return;}
   inflight=true;setNotice('Đang lưu tiến độ…');
   try{
    if(!await loadUser())throw new Error('Đăng nhập lại để lưu tiến độ.');
    const response=await csrfRequest(`playback/episodes/${episodeId}/progress`,'PUT',{job_id:config.job_id,position_ms:position,version});
    if(response.status===409){blocked=true;throw new Error('Tiến độ hoặc video đã thay đổi. Tải lại trang để đồng bộ.');}
    if(!response.ok)throw new Error(await errorMessage(response));
    const saved=await response.json();version=saved.version;lastPosition=position;
    if(!disposed&&!pending)setNotice('Đã lưu tiến độ xem.');
   }catch(e){if(!disposed)setNotice(e instanceof Error?e.message:'Chưa lưu được tiến độ.');}
   finally{inflight=false;if(pending){pending=false;void save();}}
  }
  function sessionError(){media.pause();media.removeAttribute('src');media.load();hls?.destroy();if(!disposed)setError('Phiên đăng nhập đã kết thúc. Vui lòng đăng nhập lại.');}
  const hidden=()=>{if(document.visibilityState==='hidden')void save();};
  document.addEventListener('visibilitychange',hidden);
  async function setup(){
   setError('');setInfo(null);setNotice('');setQuality('-1');setSubtitle('');setPlaying(false);
   try{
    if(!await loadUser())throw new Error('Vui lòng đăng nhập để xem video.');
    const response=await fetch(`/api/playback/episodes/${episodeId}`,{cache:'no-store'});
    if(!response.ok)throw new Error(await errorMessage(response));
    config=await response.json();if(disposed)return;
    version=config.progress.version;lastPosition=config.progress.completed?0:config.progress.position_ms;
    setInfo(config);
    listen('loadedmetadata',()=>{if(!initialized){media.currentTime=Math.min(lastPosition/1000,Math.max(0,media.duration-0.1));initialized=true;}});
    listen('play',()=>{touched=true;setPlaying(true);});listen('pause',()=>{setPlaying(false);void save();});
    listen('seeked',()=>void save());listen('ended',()=>{setPlaying(false);void save();});
    const source=`/api/playback/jobs/${config.job_id}/media/master.m3u8`;
    if(Hls.isSupported()){
     hls=new Hls({enableWorker:false,maxBufferLength:30,startPosition:lastPosition/1000});engine.current=hls;
     hls.on(Hls.Events.ERROR,(_event,data)=>{
      if(!data.fatal||disposed)return;
      if(data.type===Hls.ErrorTypes.NETWORK_ERROR&&recoveries++<2){
       void loadUser().then(user=>{if(disposed)return;if(!user)sessionError();else hls?.startLoad(media.currentTime);}).catch(()=>{if(!disposed)setError('Mạng bị gián đoạn. Chọn tải lại video để thử lại.');});
      }else if(data.type===Hls.ErrorTypes.MEDIA_ERROR&&recoveries++<2){hls?.recoverMediaError();}
      else{hls?.stopLoad();setError('Không phát được video. Kiểm tra kết nối rồi tải lại video.');}
     });
     hls.loadSource(source);hls.attachMedia(media);
    }else if(media.canPlayType('application/vnd.apple.mpegurl')){media.src=source;listen('error',()=>setError('Không phát được video. Tải lại video để thử lại.'));}
    else throw new Error('Trình duyệt chưa hỗ trợ HLS. Hãy dùng trình duyệt có MediaSource hoặc HLS.');
    timer=setInterval(()=>void save(),10000);
    authTimer=setInterval(()=>{void loadUser().then(user=>{if(!disposed&&!user)sessionError();}).catch(()=>{});},60000);
   }catch(e){if(!disposed)setError(e instanceof Error?e.message:'Không tải được video.');}
  }
  void setup();
  return()=>{disposed=true;clearInterval(timer);clearInterval(authTimer);document.removeEventListener('visibilitychange',hidden);handlers.forEach(([name,handler])=>media.removeEventListener(name,handler));hls?.destroy();engine.current=null;media.pause();media.removeAttribute('src');media.load();};
 },[episodeId,retry]);
 function selectQuality(value:string){
  setQuality(value);const media=video.current;if(!media||!info)return;
  if(engine.current){engine.current.currentLevel=Number(value);return;}
  const position=media.currentTime,wasPlaying=!media.paused;
  const asset=value==='-1'?'master.m3u8':`${info.variants[Number(value)].profile}/index.m3u8`;
  media.addEventListener('loadedmetadata',()=>{media.currentTime=position;if(wasPlaying)void media.play().catch(()=>{});},{once:true});
  media.src=`/api/playback/jobs/${info.job_id}/media/${asset}`;media.load();
 }
 function selectSubtitle(value:string){setSubtitle(value);const media=video.current;if(media)Array.from(media.textTracks).forEach(t=>{t.mode=t.language===value?'showing':'disabled';});}
 return <section className="watch-page"><Link href={info?`/movies/${info.movie_slug}`:'/movies'} className="text-link">← Về trang phim</Link>
  <p className="eyebrow">{info?.movie_title??'SUNI CINEMA'}</p><h1>{info?.title??'Trình phát video'}</h1>
  {error&&<div role="alert" className="admin-error"><p>{error}</p><Link href="/login">Đăng nhập</Link> · <button onClick={()=>setRetry(n=>n+1)}>Tải lại video</button></div>}
  <video ref={video} controls playsInline preload="metadata" aria-label="Video phim" onError={()=>{}}>
   {info?.subtitles.map(t=><track key={`${info.job_id}-${t.language}`} kind="subtitles" srcLang={t.language} label={t.label} src={`/api/playback/jobs/${info.job_id}/subtitles/${t.language}`} onLoad={()=>selectSubtitle(subtitle)}/>)}
  </video>
  {info&&<><div className="player-controls"><button onClick={()=>{const media=video.current;if(media){if(media.paused)void media.play().catch(()=>setError('Chọn phát lại để bắt đầu video.'));else media.pause();}}}>{playing?'Tạm dừng video':'Phát video'}</button>
   <label>Chất lượng<select aria-label="Chất lượng" value={quality} onChange={e=>selectQuality(e.target.value)}><option value="-1">Tự động</option>{info.variants.map((v,i)=><option key={v.profile} value={i}>{v.height}p</option>)}</select></label>
   <label>Phụ đề<select aria-label="Phụ đề" value={subtitle} onChange={e=>selectSubtitle(e.target.value)}><option value="">Tắt</option>{info.subtitles.map(t=><option key={t.language} value={t.language}>{t.label}</option>)}</select></label>
  </div>{!info.progress.completed&&info.progress.position_ms>0&&<p>Tiếp tục từ {Math.floor(info.progress.position_ms/1000)} giây.</p>}<p role="status">{notice||'Tiến độ được lưu khi tạm dừng và trong lúc xem.'}</p></>}
 </section>;
}
