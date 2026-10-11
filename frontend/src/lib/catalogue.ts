export type Movie = {slug:string; title:string; synopsis:string; release_year:number|null; required_plan_code:string; poster_url:string|null; trailer_url:string|null; genres:string[]};
export type MovieList = {items:Movie[]; total:number; page:number; page_size:number};
export type EpisodeList={items:{id:string;title:string;season_number:number;episode_number:number;ready:boolean}[];total:number;page:number;page_size:number};
export function getEpisodes(slug:string,page=1){return request<EpisodeList>(`/movies/${encodeURIComponent(slug)}/episodes?page=${page}`);}
export type Search = {q:string; page:number; sort:'newest'|'title'};
export function parseSearch(params:Record<string,string|string[]|undefined>):Search|null {
  const {q='',page='1',sort='newest'}=params;
  if(typeof q!=='string'||q.length>100||typeof page!=='string'||!/^[1-9]\d{0,3}$/.test(page)||Number(page)>1000||(sort!=='newest'&&sort!=='title')) return null;
  return {q:q.trim().normalize('NFC'),page:Number(page),sort};
}
export function moviesHref(search:Search){return `/movies?${new URLSearchParams({q:search.q,sort:search.sort,page:String(search.page)})}`;}
async function request<T>(path:string):Promise<{data:T|null;status:number}>{
  const base=process.env.API_INTERNAL_URL;
  if(!base)return {data:null,status:503};
  try{const response=await fetch(`${base}${path}`,{cache:'no-store',signal:AbortSignal.timeout(4000)});return {data:response.ok?await response.json() as T:null,status:response.status};}catch{return {data:null,status:503};}
}
export function getMovies(search:Search,size=24){return request<MovieList>(`/movies?${new URLSearchParams({q:search.q,page:String(search.page),sort:search.sort,page_size:String(size)})}`);}
export function getMovie(slug:string){
  if(!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)||slug.length>200)return Promise.resolve({data:null,status:404});
  return request<Movie>(`/movies/${encodeURIComponent(slug)}`);
}
