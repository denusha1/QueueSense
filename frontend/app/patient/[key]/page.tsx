import { PatientStatus } from '../../../components/patient-status';
export const metadata={title:'QueueSense · Your token'};
export default async function Patient({params}:{params:Promise<{key:string}>}){return <PatientStatus tokenKey={(await params).key}/>;}
