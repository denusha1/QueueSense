'use client';
import {Children,cloneElement,isValidElement,useId,useState,type ReactElement,type ReactNode} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';

type Element=ReactElement<{children?:ReactNode}>;
const isTag=(node:ReactNode,tag:string):node is Element=>isValidElement<{children?:ReactNode}>(node)&&node.type===tag;
const PAGE_SIZE=10;

/** Paginate existing table rows without changing cell content or action handlers. */
export function PaginatedTable({children,resetKey,label='Table',scrollClassName='table-scroll',total,serverPage,onPageChange}:{children:ReactNode;resetKey?:string;label?:string;scrollClassName?:string;total?:number;serverPage?:number;onPageChange?:(page:number)=>void}){
 const id=useId();
 const nodes=Children.toArray(children);
 const table=nodes.find(node=>isTag(node,'table')) as Element|undefined;
 const body=table?Children.toArray(table.props.children).find(node=>isTag(node,'tbody')) as Element|undefined:undefined;
 const rows=body?Children.toArray(body.props.children):[];
 const count=total??rows.length;
 const pages=Math.max(1,Math.ceil(count/PAGE_SIZE));
 const identity=resetKey??rows.map(row=>isValidElement(row)?row.key:'').join('|');
 const [selection,setSelection]=useState({identity,page:1});
 const page=serverPage??(selection.identity===identity?Math.min(selection.page,pages):1);
 // Reset filters and clamp shrinking data before committing rows to the screen.
 if(!onPageChange&&(selection.identity!==identity||selection.page!==page))setSelection({identity,page});
 const first=(page-1)*PAGE_SIZE;
 const visible=onPageChange?rows:rows.slice(first,first+PAGE_SIZE);
 const change=(next:number)=>onPageChange?onPageChange(next):setSelection({identity,page:next});
 const content=nodes.map(node=>isTag(node,'table')?cloneElement(node,{children:Children.map(node.props.children,child=>isTag(child,'tbody')?cloneElement(child,{children:visible}):child)}):node);
 return <div className="paginated-table"><div className={scrollClassName} id={id}>{content}</div><PageControls count={count} page={page} change={change} label={label} controlsId={id}/></div>;
}

function PageControls({count,page,change,label,controlsId}:{count:number;page:number;change:(page:number)=>void;label:string;controlsId:string}){
 const pages=Math.max(1,Math.ceil(count/PAGE_SIZE));
 const first=(page-1)*PAGE_SIZE;
 const pageNumbers=[...new Set([1,page-1,page,page+1,pages])].filter(n=>n>=1&&n<=pages).sort((a,b)=>a-b);
 return count>PAGE_SIZE?<div className="table-pagination"><p className="table-page-summary" role="status" aria-live="polite">Showing <strong>{first+1}–{Math.min(first+PAGE_SIZE,count)}</strong> of <strong>{count}</strong> records</p><nav aria-label={label+' pages'} aria-controls={controlsId}><button type="button" className="table-page-arrow" aria-label="Previous page" disabled={page===1} onClick={()=>change(page-1)}><ChevronLeft size={16}/><span>Previous</span></button><div className="table-page-numbers">{pageNumbers.map((n,i)=><span key={n}>{i>0&&n-pageNumbers[i-1]>1&&<span className="table-page-gap" aria-hidden="true">…</span>}<button type="button" aria-label={'Go to page '+n} aria-current={n===page?'page':undefined} onClick={()=>change(n)}>{n}</button></span>)}</div><span className="table-page-mobile">{page} / {pages}</span><button type="button" className="table-page-arrow" aria-label="Next page" disabled={page===pages} onClick={()=>change(page+1)}><span>Next</span><ChevronRight size={16}/></button></nav></div>:null;
}

/** Keep card actions intact while showing ten filtered items per page. */
export function PaginatedCards({children,resetKey,empty,label='Cards'}:{children:ReactNode;resetKey:string;empty?:ReactNode;label?:string}){
 const id=useId();const items=Children.toArray(children);
 const pages=Math.max(1,Math.ceil(items.length/PAGE_SIZE));
 const [selection,setSelection]=useState({identity:resetKey,page:1});
 const page=selection.identity===resetKey?Math.min(selection.page,pages):1;
 if(selection.identity!==resetKey||selection.page!==page)setSelection({identity:resetKey,page});
 return <div className="paginated-cards"><div className="board-grid" id={id}>{items.length?items.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE):empty}</div><PageControls count={items.length} page={page} change={next=>setSelection({identity:resetKey,page:next})} label={label} controlsId={id}/></div>;
}
