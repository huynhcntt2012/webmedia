import Link from 'next/link';
import {CatalogueShell} from '../components/catalogue';
export default function NotFound(){return <CatalogueShell><section className="catalogue-message"><p className="eyebrow">404</p><h1>Không tìm thấy trang</h1><p>Phim hoặc trang này hiện không có trong thư viện.</p><Link className="button" href="/movies">Về thư viện phim</Link></section></CatalogueShell>;}
