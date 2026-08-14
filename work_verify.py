import json

with open(r'C:\Users\huangl\Desktop\SMI\smi\web\public\data\daily\2026\2026-07-17.json', encoding='utf-8') as f:
    d = json.load(f)
print('tradeDate:', d['tradeDate'], '| overall:', d['overallStatus'], '| meta:', d['meta']['sourceSystem'])
for k, v in d['modules'].items():
    st = v.get('status')
    extra = ''
    if k == 'marketIndex':
        extra = ' items=%d' % len(v.get('items', []))
    if k == 'turnover':
        extra = ' today=%s' % v.get('turnoverToday')
    if k == 'sentiment':
        extra = ' rise=%s fall=%s zt=%s' % (v.get('riseCount'), v.get('fallCount'), v.get('nonStLimitUpCount'))
    if k == 'sectorPerformance':
        extra = ' top5=%d bottom5=%d ctop5=%d' % (len(v.get('industryTop5', [])), len(v.get('industryBottom5', [])), len(v.get('conceptTop5', [])))
    if k == 'fundFlow':
        extra = ' in=%d out=%d stkIn=%d' % (len(v.get('industryInflowTop10', [])), len(v.get('industryOutflowTop10', [])), len(v.get('stockInflowTop10', [])))
    if k == 'northbound':
        extra = ' mode=%s legacy=%d' % (v.get('mode'), len(v.get('legacyImportedFields', {}).get('netBuyTop10', [])))
    if k == 'margin':
        extra = ' bal=%s' % v.get('marginBalance')
    if k == 'tracks':
        extra = ' items=%d' % len(v.get('items', []))
    if k == 'summary':
        extra = ' gen=%s' % v.get('generator')
    print('  %s: %s%s' % (k, st, extra))
