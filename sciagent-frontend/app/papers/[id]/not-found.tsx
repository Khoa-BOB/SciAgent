import Link from "next/link";

export default function PaperNotFound() {
  return (
    <div className="flex flex-col items-start gap-2">
      <h1 className="text-xl font-semibold">Paper not found</h1>
      <p className="text-sm text-neutral-500">
        There&apos;s no paper with that arXiv ID in the graph.
      </p>
      <Link href="/" className="text-sm underline underline-offset-2">
        Back to search
      </Link>
    </div>
  );
}
