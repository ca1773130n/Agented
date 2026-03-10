import { describe, it, expect, beforeEach } from 'vitest';
import { usePagination } from '../usePagination';

beforeEach(() => {
  sessionStorage.clear();
});

describe('usePagination', () => {
  it('starts at page 1 with default page size of 25', () => {
    const p = usePagination();
    expect(p.currentPage.value).toBe(1);
    expect(p.pageSize.value).toBe(25);
  });

  it('computes totalPages based on totalCount and pageSize', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 35;
    expect(p.totalPages.value).toBe(4); // ceil(35/10)
  });

  it('computes offset from current page and page size', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 50;
    p.goToPage(3);
    expect(p.offset.value).toBe(20); // (3-1) * 10
  });

  it('navigates with nextPage and prevPage', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 50;

    p.nextPage();
    expect(p.currentPage.value).toBe(2);
    expect(p.isFirstPage.value).toBe(false);

    p.prevPage();
    expect(p.currentPage.value).toBe(1);
    expect(p.isFirstPage.value).toBe(true);
  });

  it('does not go below page 1 or above totalPages', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 20;

    p.prevPage(); // already at page 1
    expect(p.currentPage.value).toBe(1);

    p.goToPage(2);
    expect(p.isLastPage.value).toBe(true);

    p.nextPage(); // already at last page
    expect(p.currentPage.value).toBe(2);
  });

  it('clamps goToPage to valid range', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 30;

    p.goToPage(100);
    expect(p.currentPage.value).toBe(3);

    p.goToPage(-5);
    expect(p.currentPage.value).toBe(1);
  });

  it('computes rangeStart and rangeEnd', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 25;

    expect(p.rangeStart.value).toBe(1);
    expect(p.rangeEnd.value).toBe(10);

    p.goToPage(3);
    expect(p.rangeStart.value).toBe(21);
    expect(p.rangeEnd.value).toBe(25); // clamped to totalCount
  });

  it('returns 0 for rangeStart/rangeEnd when empty', () => {
    const p = usePagination();
    p.totalCount.value = 0;
    expect(p.rangeStart.value).toBe(0);
    expect(p.rangeEnd.value).toBe(0);
    expect(p.totalPages.value).toBe(0);
  });

  it('resets to page 1 with resetToFirstPage', () => {
    const p = usePagination({ defaultPageSize: 10 });
    p.totalCount.value = 50;
    p.goToPage(3);
    p.resetToFirstPage();
    expect(p.currentPage.value).toBe(1);
  });

  it('restores pageSize from sessionStorage', () => {
    const key = 'test-pagination';
    sessionStorage.setItem(key, '50');
    const p = usePagination({ storageKey: key, pageSizeOptions: [10, 25, 50] });
    expect(p.pageSize.value).toBe(50);
  });
});
