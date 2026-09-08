import { useEffect, useRef, useState } from 'react';
// Plotly is copied from the research environment, so charts need no CDN.
declare global {
  interface Window {
    Plotly: {
      react: (
        element: HTMLElement,
        data: Record<string, unknown>[],
        layout: Record<string, unknown>,
        config: Record<string, unknown>,
      ) => Promise<void>;
      Plots: { resize: (element: HTMLElement) => Promise<void> };
      purge: (element: HTMLElement) => void;
    };
  }
}
let loading: Promise<void> | undefined;
function loadPlotly() {
  if (window.Plotly) return Promise.resolve();
  if (!loading)
    loading = new Promise<void>((resolve, reject) => {
      const s = document.createElement('script');
      s.src = './plotly.min.js';
      s.onload = () => resolve();
      s.onerror = () => {
        loading = undefined;
        reject(Error('Chart library could not load.'));
      };
      document.head.appendChild(s);
    });
  return loading;
}
export default function Plot({
  data,
  layout,
  id,
  height = 470,
}: {
  data: Record<string, unknown>[];
  layout: Record<string, unknown>;
  id: string;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let stale = false;
    loadPlotly()
      .then(() => {
        if (stale || !ref.current) return;
        setError('');
        return window.Plotly.react(
          ref.current,
          data,
          {
            autosize: true,
            height,
            paper_bgcolor: 'transparent',
            plot_bgcolor: '#fff',
            font: {
              family: 'Inter, system-ui, sans-serif',
              size: 11,
              color: '#5f747b',
            },
            margin: { l: 66, r: 24, t: 25, b: 45 },
            hovermode: 'closest',
            showlegend: false,
            xaxis: { gridcolor: '#edf1f2' },
            yaxis: { gridcolor: '#edf1f2', automargin: true },
            ...layout,
          },
          {
            responsive: true,
            displaylogo: false,
            scrollZoom: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            toImageButtonOptions: { format: 'png', filename: id, scale: 2 },
          },
        );
      })
      .catch((e) => !stale && setError(e.message));
    return () => {
      stale = true;
    };
  }, [data, layout, id, height]);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let disposed = false;
    const observer = new ResizeObserver(() => {
      if (
        !disposed &&
        el.isConnected &&
        el.clientWidth > 0 &&
        el.clientHeight > 0 &&
        window.Plotly &&
        el.querySelector('.svg-container')
      )
        window.Plotly.Plots.resize(el).catch((e: Error) => {
          if (!disposed && el.isConnected) setError(e.message);
        });
    });
    observer.observe(el);
    return () => {
      disposed = true;
      observer.disconnect();
      if (window.Plotly) window.Plotly.purge(el);
    };
  }, []);
  return (
    <div className="plot-shell" style={{ minHeight: height }}>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div ref={ref} data-chart={id} style={{ width: '100%', height }} />
    </div>
  );
}
