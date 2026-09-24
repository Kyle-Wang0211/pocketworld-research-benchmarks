import json,sys
def inl(items):
    out=[]
    for it in items or []:
        t=it.get('type')
        if t=='text': out.append(it['text'])
        elif t=='codeVoice': out.append('`'+it['code']+'`')
        elif t in('emphasis','strong'): out.append(inl(it.get('inlineContent')))
        elif t=='reference': out.append('['+it.get('identifier','').split('/')[-1]+']')
        elif t=='link': out.append(it.get('title',''))
        else: out.append(inl(it.get('inlineContent')))
    return ''.join(out)
def blocks(bs,ind=''):
    for b in bs or []:
        t=b.get('type')
        if t=='paragraph': print(ind+inl(b.get('inlineContent')))
        elif t=='heading': print(ind+'## '+b.get('text',''))
        elif t=='aside': print(ind+'[ASIDE '+b.get('name',b.get('style',''))+']'); blocks(b.get('content'),ind+'  ')
        elif t in('unorderedList','orderedList'):
            for i in b.get('items',[]): blocks(i.get('content'),ind+' - ')
        elif t=='codeListing': print(ind+'CODE: '+'\n'.join(b.get('code',[])))
        elif t=='termList':
            for i in b.get('items',[]): print(ind+'TERM '+inl(i['term']['inlineContent'])); blocks(i['definition']['content'],ind+'   ')
        elif t=='table':
            for r in b.get('rows',[]): print(ind+' | '.join(' '.join(inl(c.get('inlineContent')) if 'inlineContent' in c else '' for c in cell) for cell in r))
        else: print(ind+'<'+t+'>')
for fn in sys.argv[1:]:
    d=json.load(open(fn))
    print('=====',fn, d.get('metadata',{}).get('title'))
    print('ABSTRACT:',inl(d.get('abstract')))
    for s in d.get('primaryContentSections',[]):
        if s.get('kind')=='content': blocks(s.get('content'))
