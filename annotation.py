import sys, io
import codecs
from lxml import etree
from collections import namedtuple
from pathlib import Path
try:
    import cPickle as pickle 
except ImportError:
    import pickle

Annotation = namedtuple('Annotation', ['id', 'sent_id', 'frame_name', 'target', 'FE'])
Target = namedtuple('Target', ['start', 'end'])
FrameElement = namedtuple('FrameElement', ['start', 'end', 'name'])

parser = etree.XMLParser(ns_clean=True)

#######################
# Remove namespace by using an XSL transformation
#######################
xslt="""<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
<xsl:output method="xml" indent="no"/>

<xsl:template match="/|comment()|processing-instruction()">
    <xsl:copy>
      <xsl:apply-templates/>
    </xsl:copy>
</xsl:template>

<xsl:template match="*">
    <xsl:element name="{local-name()}">
      <xsl:apply-templates select="@*|node()"/>
    </xsl:element>
</xsl:template>

<xsl:template match="@*">
    <xsl:attribute name="{local-name()}">
      <xsl:value-of select="."/>
    </xsl:attribute>
</xsl:template>
</xsl:stylesheet>
"""

xslt_doc=etree.parse(io.BytesIO(xslt))
transform=etree.XSLT(xslt_doc)

    
def parse_fulltext(path):
    """
    Return the annotations of sentences that contain at least one manual annotation
    
    It's something like:
    [(sentence_string, [annotation1, anntatation2]), (....), (....)]
    
    >>> result = parse_fulltext("test_data/annotation.xml")
    >>> len(result)
    1
    >>> len(result[0])
    2
    >>> result[0][0]
    u'Your contribution to Goodwill will mean more than you may know .'
    >>> result[0][1][0]
    Annotation(id='2024608', sent_id='1281539', frame_name='Giving', target=Target(start=5, end=16), FE=[FrameElement(start=0, end=3, name='Donor'), FrameElement(start=18, end=28, name='Recipient')])
    >>> result[0][1][1]
    Annotation(id='2024610', sent_id='1281539', frame_name='Purpose', target=Target(start=35, end=38), FE=[FrameElement(start=0, end=28, name='Means'), FrameElement(start=40, end=61, name='Value')])
    
    # for DNI etc cases
    >>> result = parse_fulltext("test_data/annotation_dni.xml")
    >>> result[0][1][0]
    Annotation(id='2018465', sent_id='1278414', frame_name='Importance', target=Target(start=60, end=63), FE=[FrameElement(start=65, end=70, name='Factor')])
    >>> result[0][1][1]
    Annotation(id='2018466', sent_id='1278414', frame_name='Rewards_and_punishments', target=Target(start=154, end=163), FE=[])
    """
    tree = etree.parse(path, parser)
    tree=transform(tree) # remove namespace
    result = []
    for sent in tree.xpath('sentence'):
        sent_id = sent.attrib['ID']
        sent_str = sent.xpath('text')[0].text.decode('utf8')
        annotations = []
        for a in sent.xpath('annotationSet[@status="MANUAL"]'):
            ann_id = a.attrib['ID']
            target_label = a.xpath('layer[@name="Target"]/label')
            if len(target_label) == 1:
                target_node = target_label[0]
            else:
                continue
                
            target = Target(start = int(target_node.attrib['start']),
                            end = int(target_node.attrib['end']))
            
            FE = []
            for label in a.xpath('layer[@name="FE"]/label[not(@itype)] '): # exclude null instantiation ones
                if 'start' in label.attrib: # if it has `start` key
                    FE.append(FrameElement(start = int(label.attrib['start']), 
                                           end = int(label.attrib['end']), 
                                           name = label.attrib['name']))

            if len(FE) == 0:
                sys.stderr.write('No FrameElement with explicit instantiation found for frame "%r" in "%s"\n' %(a.attrib['frameName'], sent_str.encode('utf8')))

            annotation = Annotation(id = ann_id,
                                    sent_id = sent_id,
                                    frame_name = a.attrib['frameName'], 
                                    target = target, 
                                    FE = FE)
            
            annotations.append(annotation)
        if len(annotations) > 0: # only those with annotations
            result.append((sent_str, annotations))

    if len(result) == 0:
        sys.stderr.write("WARNING: no result found for %s" %(path))

    return result

def align_annotation_with_sentence(sent, new_sent, annotations):
    """align the annotation element offset from the old sentence to new one
    
    >>> from nltk.tree import Tree
    >>> sent = 'he says: I say: I love you'
    >>> tree = Tree('ROOT', ['he', 'says', ':', 'I', 'say', ':', 'I', 'love', 'you'])
    >>> anns = [Annotation(id='1', sent_id='1', frame_name='he', target=Target(start=0, end=1), FE=[FrameElement(start=3, end=6, name='says'), FrameElement(start=7, end=7, name=':')]), \
    Annotation(id='2', sent_id='2', frame_name='I', target=Target(start=9, end=9), FE=[FrameElement(start=14, end=14, name=':'), FrameElement(start=16, end=16, name='I'), FrameElement(start=11, end=16, name='say: I')])]
    >>> align_annotation_with_sentence(sent, ' '.join(tree.leaves()), anns)
    [Annotation(id='1', sent_id='1', frame_name='he', target=Target(start=0, end=1), FE=[FrameElement(start=3, end=6, name='says'), FrameElement(start=8, end=8, name=':')]), Annotation(id='2', sent_id='2', frame_name='I', target=Target(start=10, end=10), FE=[FrameElement(start=16, end=16, name=':'), FrameElement(start=18, end=18, name='I'), FrameElement(start=12, end=18, name='say: I')])]
    
    >>> sent = ' '.join(tree.leaves())
    >>> align_annotation_with_sentence(sent, sent, anns)
    [Annotation(id='1', sent_id='1', frame_name='he', target=Target(start=0, end=1), FE=[FrameElement(start=3, end=6, name='says'), FrameElement(start=7, end=7, name=':')]), Annotation(id='2', sent_id='2', frame_name='I', target=Target(start=9, end=9), FE=[FrameElement(start=14, end=14, name=':'), FrameElement(start=16, end=16, name='I'), FrameElement(start=11, end=16, name='say: I')])]
    """
    if sent == new_sent:
        return annotations
    
    gaps = []
    i,j = 0,0
    while i < len(sent) and j <len(new_sent):
        if sent[i] != new_sent[j]:
            gaps.append(i)
            j += 1
        else:
            i += 1
            j += 1

    new_anns = []
    
    def correct_pos(pos):
        for i in xrange(len(gaps)):
            if pos < gaps[i]:
                return pos + i 
        return pos + i + 1

    for ann in annotations:
        new_target = Target(correct_pos(ann.target.start), correct_pos(ann.target.end))
        fes = []
        for fe in ann.FE:
            fes.append(FrameElement(correct_pos(fe.start), correct_pos(fe.end), fe.name))

        new_anns.append(Annotation(ann.id, ann.sent_id, ann.frame_name, new_target, fes))

    return new_anns
    
def distribute_annotations(annotations, output_dir, print_sent_path = False):
    """
    Distribute the `annotations` to seperate files under `output_dir`

    >>> from pathlib import Path
    >>> from pickle import load
    >>> anns = parse_fulltext("test_data/annotation.xml")
    >>> output_dir = 'test_data/individual_annotations'
    >>> distribute_annotations(anns, output_dir)
    >>> Path(output_dir + '/' + anns[0][1][0].sent_id + '.txt').open().read()
    u'Your contribution to Goodwill will mean more than you may know .'
    >>> load(Path(output_dir + '/' + anns[0][1][0].id + '.ann').open())
    Annotation(id='2024608', sent_id='1281539', frame_name='Giving', target=Target(start=5, end=16), FE=[FrameElement(start=0, end=3, name='Donor'), FrameElement(start=18, end=28, name='Recipient')])
    >>> list(Path(output_dir).glob('*.txt'))
    [PosixPath('test_data/individual_annotations/1281539.txt')]
    >>> list(Path(output_dir).glob('*.ann'))
    [PosixPath('test_data/individual_annotations/2024608.ann'), PosixPath('test_data/individual_annotations/2024610.ann')]
    >>> import shutil
    >>> shutil.rmtree(output_dir)
    """
    d = Path(output_dir)
    if not d.exists():
        d.mkdir()

    for sent, anns in annotations:
        sent_id = anns[0].sent_id
        sent_dir = output_dir + '/' + sent_id + '.txt'
        if print_sent_path:
            print sent_dir
        with codecs.open(sent_dir, 'w', 'utf8') as f:
            f.write(sent)

        for ann in anns:
            with open(output_dir + '/' + ann.id + '.ann', 'w') as f:
                pickle.dump(ann, f)
