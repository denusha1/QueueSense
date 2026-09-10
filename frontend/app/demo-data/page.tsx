import type { Metadata } from 'next';
import dataset from '../../../data/sample/summary.json';
import { DataPreview } from '../../components/data-preview';

export const metadata: Metadata = { title: 'QueueSense · Demo dataset' };
export default function DemoDataPage() {
  return <DataPreview data={dataset} />;
}
