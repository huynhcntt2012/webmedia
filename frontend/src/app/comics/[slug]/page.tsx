import {CatalogueShell} from '../../../components/catalogue';
import {ComicLibrary} from '../../../components/comic-library';
export const dynamic='force-dynamic';
export default async function Page({params}:{params:Promise<{slug:string}>}){const {slug}=await params;return <CatalogueShell><ComicLibrary key={slug} slug={slug}/></CatalogueShell>;}
