import { SelfCheckin } from '../../../components/arrivals';
export const metadata = { title: 'QueueSense · Self check-in', robots: { index: false, follow: false }, referrer: 'no-referrer' as const };
export default async function Page({ params }: { params: Promise<{ key: string }> }) {
 return <SelfCheckin tokenKey={(await params).key}/>;
}
