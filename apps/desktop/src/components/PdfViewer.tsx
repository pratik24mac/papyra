// Renders a PDF (as bytes) page by page with pdf.js. Same rendering on Windows and macOS,
// independent of the WebView's own PDF support.
import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Alert, Spin, Typography } from "antd";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export function PdfViewer({ data, width = 760 }: { data: ArrayBuffer | null; width?: number }) {
  const container = useRef<HTMLDivElement>(null);
  const [pages, setPages] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!data || !container.current) return;
    let cancelled = false;
    const host = container.current;
    host.innerHTML = "";
    setPages(null); setError(null);
    (async () => {
      try {
        const pdf = await pdfjs.getDocument({ data: data.slice(0) }).promise;
        if (cancelled) return;
        setPages(pdf.numPages);
        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const base = page.getViewport({ scale: 1 });
          const scale = (width / base.width) * (window.devicePixelRatio || 1);
          const viewport = page.getViewport({ scale });
          const canvas = document.createElement("canvas");
          canvas.width = viewport.width; canvas.height = viewport.height;
          canvas.style.width = `${width}px`; canvas.style.height = `${(viewport.height / viewport.width) * width}px`;
          canvas.style.display = "block"; canvas.style.margin = "0 auto 16px"; canvas.style.boxShadow = "0 1px 6px rgba(0,0,0,.25)";
          canvas.setAttribute("aria-label", `Page ${i} of ${pdf.numPages}`);
          host.appendChild(canvas);
          await page.render({ canvas, canvasContext: canvas.getContext("2d")!, viewport }).promise;
          if (cancelled) return;
        }
      } catch (e) {
        if (!cancelled) setError(String((e as Error)?.message ?? e));
      }
    })();
    return () => { cancelled = true; };
  }, [data, width]);

  if (error) return <Alert type="error" showIcon message="The PDF could not be displayed" description={error} />;
  return (
    <div>
      {!data || pages === null ? <Spin /> : <Typography.Text type="secondary">{pages} page{pages === 1 ? "" : "s"}</Typography.Text>}
      <div ref={container} data-testid="pdf-pages" style={{ background: "#101012", borderRadius: 12, padding: 16, marginTop: 8, maxHeight: "70vh", overflow: "auto" }} />
    </div>
  );
}
