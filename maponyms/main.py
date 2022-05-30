
from . import segmentation
from . import toponyms
from . import triangulate

import mapocr

import PIL, PIL.Image

import datetime
import time
import math
import os
import json
import itertools
import warnings

# PY3 Fix
try: 
    basestring
except:
    basestring = (bytes,str)


### FUNCS FOR DIFFERENT STAGES

def image_partitioning(im):
    ################
    # Image partitioning
    
    # partition image
    mapp_poly,box_polys = segmentation.image_segments(im)

    # create as feature collection (move to image_segments()?)
    seginfo = {'type': 'FeatureCollection',
               'features': []}
    
    # (map)
    if mapp_poly is not None:
        mapp_geoj = {'type': 'Polygon',
                     'coordinates': [ [tuple(p[0].tolist()) for p in mapp_poly] ]}
        props = {'type':'Map'}
        feat = {'type': 'Feature', 'properties': props, 'geometry': mapp_geoj}
        seginfo['features'].append(feat)
        
    
    # (boxes)
    if box_polys:
        boxes_geoj = [{'type': 'Polygon',
                     'coordinates': [ [tuple(p[0].tolist()) for p in box] ]}
                      for box in box_polys]
        for box_geoj in boxes_geoj:
            props = {'type':'Box'}
            feat = {'type': 'Feature', 'properties': props, 'geometry': box_geoj}
            seginfo['features'].append(feat)

    # debug extracted segments...
##    import pythongis as pg
##    d = pg.VectorData()
##    for geoj in seginfo['features']:
##        d.add_feature([], geoj['geometry'])
##    d.view(fillcolor=None)

    return seginfo

def text_detection(text_im, textcolor, **kwargs):
    ###############
    # Text detection
    verbose = kwargs.get('verbose')
    
    # detect text
    if verbose:
        print('(detecting text)')
    if textcolor and isinstance(textcolor, (tuple,list)) and isinstance(textcolor[0], (int,float)):
        textcolor = [textcolor]
    textcolor = [tuple(c) for c in textcolor]
    texts = mapocr.textdetect.auto_detect_text(text_im, textcolor=textcolor, **kwargs)
    toponym_colors = set((tuple(r['color']) for r in texts))

    # deduplicate overlapping texts from different colors
    # very brute force...
    if len(toponym_colors) > 1:
        if verbose:
            print('(deduplicating texts of different colors)')
            print('textlen',len(texts))
        # for every combination of text colors
        for col,col2 in itertools.combinations(toponym_colors, 2):
            coltexts = [r for r in texts if r['color'] == col]
            coltexts2 = [r for r in texts if r['color'] == col2]
            if verbose:
                print('comparing textcolor',map(int,col),len(coltexts),'with',map(int,col2),len(coltexts2))
            # we got two different colored groups of text
            for r in coltexts:
                for r2 in coltexts2:
                    # find texts that overlap
                    if not (r['left'] > (r2['left']+r2['width']) \
                            or (r['left']+r['width']) < r2['left'] \
                            or r['top'] > (r2['top']+r2['height']) \
                            or (r['top']+r['height']) < r2['top'] \
                            ):
                        # drop the one with the poorest color match
                        #text_im.crop((r['left'], r['top'], r['left']+r['width'], r['top']+r['height'])).show()
                        #text_im.crop((r2['left'], r2['top'], r2['left']+r2['width'], r2['top']+r2['height'])).show()
                        if r2['color_match'] > r['color_match'] and not math.isnan(r2['color_match']):
                            r2['drop'] = True
                            if verbose:
                                print(u'found duplicate texts of different colors, keeping "{}" (color match={:.2f}), dropping "{}" (color match={:.2f})'.format(r['text_clean'],r['color_match'],r2['text_clean'],r2['color_match']))
                        else:
                            r['drop'] = True
                            if verbose:
                                print(u'found duplicate texts of different colors, keeping "{}" (color match={:.2f}), dropping "{}" (color match={:.2f})'.format(r2['text_clean'],r2['color_match'],r['text_clean'],r['color_match']))
        texts = [r for r in texts if not r.get('drop')]
        if verbose:
            print('textlen deduplicated',len(texts))

    # connect texts
    if verbose:
        print('(connecting texts)')
    grouped = []
    # connect each color texts separately
    for col in toponym_colors:
        coltexts = [r for r in texts if r['color'] == col]
        # divide into lower and upper case subgroups
        # upper = more than half of alpha characters is uppercase (to allow for minor ocr upper/lower errors)
        lowers = []
        uppers = []
        for text in coltexts:
            alphachars = text['text_alphas']
            isupper = len([ch for ch in alphachars if ch.isupper()]) > (len(alphachars) / 2.0) 
            if isupper:
                uppers.append(text)
            else:
                lowers.append(text)
        # connect lower and upper case texts separately
        if len(lowers) > 1:
            grouped.extend( mapocr.textgroup.connect_text(lowers) )
        if len(uppers) > 1:
            grouped.extend( mapocr.textgroup.connect_text(uppers) )
    texts = grouped

    # store metadata
    textinfo = {'type': 'FeatureCollection', 'features': []}
    for r in texts:
        x1,y1,x2,y2 = r['left'], r['top'], r['left']+r['width'], r['top']+r['height']
        box = [(x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1)]
        geoj = {'type':'Polygon', 'coordinates':[box]}
        props = dict(r)
        feat = {'type':'Feature', 'geometry':geoj, 'properties':props}
        textinfo['features'].append(feat)

    return textinfo

def toponym_selection(im, textinfo, seginfo=None, must_have_anchor=False, verbose=False):
    ################
    # Toponym selection
    texts = [f['properties'] for f in textinfo['features']]

    # filter toponym candidates
    if verbose:
        print('filtering toponym candidates')
    topotexts = toponyms.filter_toponym_candidates(texts, seginfo)

    # text anchor points
    if verbose:
        print('determening toponym anchors')
    topotexts = toponyms.detect_toponym_anchors(im, texts, topotexts)

    # create control points from toponyms
    points = []
    for r in topotexts:
        name = r['text_clean']
        if 'anchor' in r:
            p = r['anchor']
        else:
            if must_have_anchor:
                # only include toponyms with anchor points
                continue
            else:
                # set missing anchor points to bbox center
                x = r['left'] + r['width'] / 2.0
                y = r['top'] + r['height'] / 2.0
                p = (x,y)
        points.append((name,p))

    # store metadata
    toponyminfo = {'type': 'FeatureCollection', 'features': []}
    for name,p in points:
        geoj = {'type':'Point', 'coordinates':p}
        props = {'name':name}
        feat = {'type':'Feature', 'geometry':geoj, 'properties':props}
        toponyminfo['features'].append(feat)

    return toponyminfo

def match_control_points(toponyminfo, **kwargs):
    ###############
    # Control point matching
    points = [(f['properties']['name'],f['geometry']['coordinates']) for f in toponyminfo['features']]

    # find matches
    matchsets = triangulate.find_matchsets(points, **kwargs)
    origs,matches = triangulate.best_matchset(matchsets)
    orignames,origcoords = zip(*origs)
    matchnames,matchcoords = zip(*matches)
    tiepoints = list(zip(origcoords, matchcoords))

    # store metadata
    gcps_matched_info = {'type': 'FeatureCollection', 'features': []}
    for (oname,ocoord),(mname,mcoord) in zip(origs,matches):
        geoj = {'type':'Point', 'coordinates':mcoord}
        props = {'origname':oname, 'origx':ocoord[0], 'origy':ocoord[1],
                 'matchname':mname, 'matchx':mcoord[0], 'matchy':mcoord[1]}
        feat = {'type':'Feature', 'geometry':geoj, 'properties':props}
        gcps_matched_info['features'].append(feat)

    return gcps_matched_info





    
