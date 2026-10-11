'use client';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {useCallback,useEffect,useState} from 'react';
import {csrfRequest,errorMessage,loadUser} from '../lib/auth-client';
type Device={id:string;created_at:string;expires_at:string;current:boolean};
type Access={plan:string;device_limit:number;expires_at:string|null};
export function Devices(){
 const router=useRouter();
 const [items,setItems]=useState<Device[]>([]),[access,setAccess]=useState<Access|null>(null),[error,setError]=useState(''),[signedIn,setSignedIn]=useState(false),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false);
 const refresh=useCallback(async()=>{const user=await loadUser();setSignedIn(!!user);if(!user){setItems([]);setAccess(null);return;}const [a,d]=await Promise.all([fetch('/api/content/access',{cache:'no-store'}),fetch('/api/content/devices',{cache:'no-store'})]);if(!a.ok)throw new Error(await errorMessage(a));if(!d.ok)throw new Error(await errorMessage(d));setAccess(await a.json());setItems((await d.json()).items);},[]);
 useEffect(()=>{async function run(){try{await refresh();setError('');}catch(e){setError((e as Error).message);}finally{setLoading(false);}}void run();const timer=setInterval(()=>void run(),30000);return()=>clearInterval(timer);},[refresh]);
 async function revoke(row:Device){if(!confirm('Đăng xuất phiên này và ngừng quyền xem/đọc?'))return;setBusy(true);setError('');try{const r=await csrfRequest(`content/devices/${row.id}`,'DELETE');if(!r.ok)throw new Error(await errorMessage(r));if(row.current){router.replace('/login');return;}await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <section className="billing"><p className="eyebrow">TÀI KHOẢN</p><h1>Thiết bị đang xem và đọc</h1><p>Mỗi phiên đăng nhập trên trình duyệt tính là một thiết bị. Phiên ngừng xem/đọc sẽ tự nhả chỗ sau tối đa 5 phút. Thu hồi sẽ đăng xuất phiên đó.</p>{loading&&<p role="status">Đang tải…</p>}{error&&<p role="alert">{error}</p>}{!loading&&!signedIn&&<Link href="/login">Đăng nhập để quản lý thiết bị →</Link>}{access&&<><p>Quyền hiện tại: <strong>{access.plan.toUpperCase()}</strong> · Tối đa {access.device_limit} thiết bị đồng thời.</p>{access.expires_at&&<p>Hết hạn: {new Date(access.expires_at).toLocaleString('vi-VN')}</p>}{items.length===0?<p>Chưa có phiên xem/đọc đang hoạt động.</p>:<ul className="billing-orders">{items.map((row,index)=><li key={row.id}><h2>{row.current?'Phiên hiện tại':`Phiên ${index+1}`}</h2><p>Bắt đầu: {new Date(row.created_at).toLocaleString('vi-VN')}</p><button disabled={busy} onClick={()=>void revoke(row)}>Thu hồi {row.current?'phiên hiện tại':`phiên ${index+1}`}</button></li>)}</ul>}</>}</section>;
}
