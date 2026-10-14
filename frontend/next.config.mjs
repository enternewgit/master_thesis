/** @type {import('next').NextConfig} */
import createNextIntlPlugin from 'next-intl/plugin';
 
const withNextIntl = createNextIntlPlugin();
const nextConfig = {
    // assetPrefix: '/braingram',
	basePath: '/braingram_mg',
	trailingSlash: true,
};
export default withNextIntl(nextConfig);
