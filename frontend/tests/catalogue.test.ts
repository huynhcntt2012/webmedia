import {describe,it,expect} from 'vitest';
import {parseSearch,moviesHref} from '../src/lib/catalogue';
describe('catalogue URL input',()=>{
 it('normalizes Vietnamese and defaults',()=>{expect(parseSearch({q:' Mùa Hè '.normalize('NFD')})).toEqual({q:'Mùa Hè',page:1,sort:'newest'});});
 it.each([{q:['x','y']},{page:'0'},{page:'1001'},{page:'1.1'},{sort:'sql'},{q:'x'.repeat(101)}])('rejects invalid query %j',params=>{expect(parseSearch(params)).toBeNull();});
 it('encodes searches and keeps pagination state',()=>{expect(moviesHref({q:'a&b',page:2,sort:'title'})).toBe('/movies?q=a%26b&sort=title&page=2');});
});
