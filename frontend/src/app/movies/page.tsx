import Link from 'next/link';
import {CatalogueShell,CatalogueMessage,MovieGrid,SearchForm} from '../../components/catalogue';
import {getMovies,moviesHref,parseSearch} from '../../lib/catalogue';
export const dynamic='force-dynamic';
export const metadata={title:'Thư viện phim — Suni AI Cinema'};
export default async function Movies({searchParams}:{searchParams:Promise<Record<string,string|string[]|undefined>>}){
 const search=parseSearch(await searchParams);
 if(!search)return <CatalogueShell><section className="catalogue-section"><h1>Tham số tìm kiếm không hợp lệ</h1><p>Tên phim tối đa 100 ký tự; trang từ 1 đến 1000.</p><Link className="button" href="/movies">Về thư viện</Link></section></CatalogueShell>;
 const {data}=await getMovies(search);const pages=data?Math.min(1000,Math.ceil(data.total/data.page_size)):0;
 return <CatalogueShell><section className="catalogue-section library-page"><p className="eyebrow">THẾ GIỚI ĐIỆN ẢNH</p><h1>Thư viện phim</h1><p className="library-intro">Một lựa chọn mới cho mỗi tâm trạng.</p><SearchForm search={search}/>{data&&<p className="result-summary" role="status">{data.total} phim{search.q?` cho “${search.q}”`:' trong thư viện'}{pages>0?` · Trang ${search.page} / ${pages}`:''}</p>}{!data?<CatalogueMessage error/>:data.items.length?<MovieGrid items={data.items}/>:search.page>1&&data.total>0?<div className="catalogue-message"><h2>Trang này chưa có phim</h2><Link className="text-link" href={moviesHref({...search,page:1})}>Về trang đầu →</Link></div>:<CatalogueMessage search={Boolean(search.q)}/>}{data&&pages>1&&<nav className="pagination" aria-label="Phân trang">{search.page>1&&<Link href={moviesHref({...search,page:search.page-1})}>← Trang trước</Link>}<span>Trang {search.page}</span>{search.page<pages&&<Link href={moviesHref({...search,page:search.page+1})}>Trang sau →</Link>}</nav>}</section></CatalogueShell>;
}
