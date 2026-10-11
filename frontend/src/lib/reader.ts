export function readingOffset(top:number,height:number){return height>0?Math.max(0,Math.min(1000,Math.round(-top/height*1000))):0;}
export function boundedPage(index:number,total:number){return Math.max(0,Math.min(Math.max(0,total-1),index));}
