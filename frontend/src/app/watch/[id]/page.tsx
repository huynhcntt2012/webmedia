import {notFound} from 'next/navigation';
import {CatalogueShell} from '../../../components/catalogue';
import {VideoPlayer} from '../../../components/video-player';
export const dynamic='force-dynamic';
export const metadata={title:'Xem phim — Suni AI Cinema'};
export default async function Watch({params}:{params:Promise<{id:string}>}){
 const {id}=await params;if(!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(id))notFound();
 return <CatalogueShell><VideoPlayer episodeId={id}/></CatalogueShell>;
}
