import type { ReactNode } from 'react';
import { buttonVariants } from '@/components/ui/button';
import { toCSV } from './utils';

export default function CsvLink({
  filename,
  rows,
  children,
  label,
}: {
  filename: string;
  rows: Record<string, unknown>[];
  children: ReactNode;
  label?: string;
}) {
  const href =
    'data:text/csv;charset=utf-8,' + encodeURIComponent('\uFEFF' + toCSV(rows));
  return (
    <a
      className={buttonVariants({ variant: 'outline' })}
      href={href}
      download={filename}
      aria-label={label}
    >
      {children}
    </a>
  );
}
