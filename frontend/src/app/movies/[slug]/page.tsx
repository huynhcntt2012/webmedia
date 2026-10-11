import Link from 'next/link';
import {Poster} from '../../../components/poster';
import {notFound} from 'next/navigation';
import {CatalogueShell,CatalogueMessage} from '../../../components/catalogue';
import {getMovie,getEpisodes} from '../../../lib/catalogue';
export const dynamic='force-dynamic';
export const metadata={title:'Chi tiết phim — Suni AI Cinema'};
export default async function MovieDetail({params,searchParams}:{params:Promise<{slug:string}>;searchParams:Promise<{page?:string}>}){
 const slug=(await params).slug;const page=Number((await searchParams).page??1);if(!Number.isInteger(page)||page<1||page>1000)notFound();
 const {data:movie,status}=await getMovie(slug);const {data:episodes}=await getEpisodes(slug,page);
 if(status===404||status===422)notFound();
 if(!movie)return <CatalogueShell><CatalogueMessage error/></CatalogueShell>;
 return <CatalogueShell><section className="movie-detail"><Link className="text-link" href="/movies">← Thư viện phim</Link><div className="detail-layout"><Poster url={movie.poster_url} title={movie.title} detail/><div><p className="eyebrow">KHÁM PHÁ BỘ PHIM</p><h1>{movie.title}</h1><div className="detail-badges"><span>{movie.release_year??'Chưa rõ năm phát hành'}</span><span>Gói {movie.required_plan_code.toUpperCase()}</span></div><p className="genre-labels">{movie.genres.join(" · ")}</p>{movie.trailer_url&&<a className="button" href={movie.trailer_url} target="_blank" rel="noopener noreferrer">Xem trailer trên YouTube ↗</a>}<h2>Nội dung phim</h2><p className="synopsis">{movie.synopsis||'Thông tin nội dung đang được cập nhật.'}</p><div className="playback-note">{!episodes?<p>Chưa tải được danh sách tập.</p>:!episodes.items.length?<><strong>Chưa có bản phát</strong><p>Video sẽ xuất hiện khi sẵn sàng.</p></>:<><h2>Các tập phim</h2><ul className="episode-list">{episodes.items.map(ep=><li key={ep.id}>{ep.ready?<Link href={`/watch/${ep.id}`}>Mùa {ep.season_number} · Tập {ep.episode_number}: {ep.title} <span>▶ Xem phim</span></Link>:<span>{ep.title} · Đang chuẩn bị video</span>}</li>)}</ul><nav aria-label="Phân trang tập">{page>1&&<Link href={`?page=${page-1}`}>Tập trước</Link>} {page*20<episodes.total&&<Link href={`?page=${page+1}`}>Tập sau</Link>}</nav></>}</div></div></div></section></CatalogueShell>;
}
