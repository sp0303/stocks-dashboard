import React from 'react';

interface Props {
  page: number;
  pages: number;
  onPage: (p: number) => void;
}

const BTN = 'px-2 py-1 border border-hairline rounded-interactive disabled:opacity-40';

export const Pager: React.FC<Props> = ({ page, pages, onPage }) => (
  <nav aria-label="Pagination" className="p-3 flex justify-end items-center gap-2 text-xs text-subtle">
    <button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className={BTN}>Prev</button>
    Page {page + 1} / {Math.max(1, pages)}
    <button type="button" disabled={page + 1 >= pages} onClick={() => onPage(page + 1)} className={BTN}>Next</button>
  </nav>
);
