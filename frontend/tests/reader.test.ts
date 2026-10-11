import {describe,expect,it} from 'vitest';
import {boundedPage,readingOffset} from '../src/lib/reader';
describe('reader viewport bounds',()=>{
 it('normalizes within image and clamps overscroll',()=>{expect(readingOffset(-300,1200)).toBe(250);expect(readingOffset(50,1200)).toBe(0);expect(readingOffset(-1500,1200)).toBe(1000);expect(readingOffset(0,0)).toBe(0);});
 it('keeps keyboard movement within available pages',()=>{expect(boundedPage(-1,5)).toBe(0);expect(boundedPage(5,5)).toBe(4);expect(boundedPage(2,5)).toBe(2);expect(boundedPage(1,0)).toBe(0);});
});
