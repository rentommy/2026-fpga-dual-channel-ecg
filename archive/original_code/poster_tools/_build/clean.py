import zipfile
from lxml import etree as E
with zipfile.ZipFile(r'D:\Desktop\AMD_poster_template.pptx') as zi, zipfile.ZipFile(r'D:\ecg_fpga\海报\_build\template_clean.pptx','w',zipfile.ZIP_DEFLATED) as zo:
    for n in zi.namelist():
        data=zi.read(n)
        if n.startswith(('ppt/slideMasters/slideMaster','ppt/slideLayouts/slideLayout')) and n.endswith('.xml'):
            d=E.fromstring(data)
            for t in d.xpath('//p:spTree',namespaces={'p':'http://schemas.openxmlformats.org/presentationml/2006/main'}):
                for x in list(t):
                    if E.QName(x).localname not in ['nvGrpSpPr','grpSpPr']: t.remove(x)
            data=E.tostring(d,xml_declaration=True,encoding='UTF-8',standalone=True)
        zo.writestr(n,data)
