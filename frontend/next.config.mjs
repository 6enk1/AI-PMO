/** @type {import('next').NextConfig} */

// GitHub Pages 用の静的書き出し。リポジトリ名のサブパス配下に置かれるので
// basePath / assetPrefix を合わせ、拡張子なしURLでも引けるよう trailingSlash を付ける。
const isPages = process.env.GITHUB_PAGES === "1";
const basePath = process.env.NEXT_BASE_PATH ?? (isPages ? "/AI-PMO" : "");

const nextConfig = {
  reactStrictMode: true,
  // standalone は Docker イメージ用、export は GitHub Pages 用。
  // ローカルの dev / start は既定の出力を使う。
  output:
    process.env.NEXT_OUTPUT === "standalone" ? "standalone" : isPages ? "export" : undefined,
  basePath: basePath || undefined,
  assetPrefix: basePath || undefined,
  trailingSlash: isPages || undefined,
  images: { unoptimized: true },
};

export default nextConfig;
