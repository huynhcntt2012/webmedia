import {CatalogueShell} from '../../components/catalogue';
export default function Loading(){return <CatalogueShell><section className="catalogue-section" aria-busy="true"><h1>Thư viện phim</h1><p role="status">Đang tải phim…</p><div className="movie-grid" aria-hidden="true">{[1,2,3,4].map(i=><div key={i} className="poster-placeholder skeleton"/>)}</div></section></CatalogueShell>;}
