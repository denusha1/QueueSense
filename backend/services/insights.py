"""Explainable operational recommendations derived from the selected cohort."""
def recommendations(report):
    result=[]
    def add(title,evidence,action):
        result.append(dict(title=title,evidence=evidence,recommendation=action))
    measured=[r for r in report['departments'] if r['average_wait'] is not None and r['completed']>=10]
    if measured:
        slow=max(measured,key=lambda r:float(r['average_wait']))
        wait=float(slow['average_wait'])
        if wait>30:
            add('Review department capacity',f"{slow['name']} averaged {wait:.1f} minutes of waiting across {slow['completed']} completed visits.",'Review staffing and service bottlenecks in this department; compare staffing scenarios before changing capacity.')
    bands=[r for r in report['heatmap'] if r['arrivals']>=10]
    if bands:
        peak=max(bands,key=lambda r:r['arrivals'])
        day=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][peak['weekday']-1]
        add('Plan for peak arrivals',f"{day} at {peak['hour']:02}:00 recorded {peak['arrivals']} arrivals in this cohort.",'Compare arrival demand with clinician schedules and consider staggered arrival slots during this band.')
    overloaded=[r for r in report['workload'] if r['completed']>=10 and r['utilization_proxy'] is not None and r['utilization_proxy']>90]
    if overloaded:
        row=max(overloaded,key=lambda r:r['utilization_proxy'])
        add('Review workload balance',f"{row['name']} has a {row['utilization_proxy']:.1f}% scheduled-capacity utilization proxy.",'Review shift coverage and workload distribution. Confirm actual working hours because cohort service can spill outside the selected hours.')
    trends=[r for r in report['trends'] if r['average_wait'] is not None and r['completed']>=10]
    if len(trends)>=2:
        split=max(1,len(trends)//2)
        def weighted(rows):
            return sum(float(r['average_wait'])*r['measured_waits'] for r in rows)/sum(r['measured_waits'] for r in rows)
        early,late=weighted(trends[:split]),weighted(trends[split:])
        if late>early+5 and late>early*1.2:
            add('Investigate rising waiting times',f'Average wait increased from {early:.1f} to {late:.1f} minutes between the earlier and later days in this selection.','Check changes in arrivals, clinician availability and service duration before attributing the increase to a single cause.')
    if not result:
        add('Continue monitoring',f"{report['summary']['arrivals']} arrivals are included in the selected cohort.",'No recommendation threshold was met. Collect more completed visits and compare another date range before changing clinic operations.')
    return result
