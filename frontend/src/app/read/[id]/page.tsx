import {CatalogueShell} from '../../../components/catalogue';
import {ComicReader} from '../../../components/comic-reader';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <CatalogueShell><ComicReader key={id} id={id}/></CatalogueShell>;}
