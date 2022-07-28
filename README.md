# Maponyms
Detects toponyms from map images.

## Installation

This library requires PIL, numpy, opencv, colormath, shapely, and mapocr and its dependencies for text recognition. 

By default, maponyms relies on a local SQLite database of gazetteer names to use for geocoding. For convenience, a version of this database can be downloaded from [this link](https://filedn.com/lvxzpqbRuTkLnAjfFXe7FFu/Gazetteer%20DB/gazetteers%202022-05-31.zip). However, this is not necessary if you choose to use another database or gazetteer backend (see more details below). 

## Extracting toponyms from a map

First, import the library:

    >>> import maponyms

Next, load the image you wish to extract toponyms from:

    >>> from PIL import Image
    >>> im = Image.open('tests/data/burkina_pol96.jpg')

![Original image](/tests/data/burkina_pol96.jpg)

In this image we are looking specifically for placename labels in and around the main map region. But there are also a lot of other text throughout the map, including the map title, legend descriptions, and text along the margins of the map. To help distinguish between toponyms and non-toponym text, it's useful to analyze the basic layout of the image into individual segments or regions. The following function detects the main map region, along with any large rectangular boxes such as the legend box, and returns this as a GeoJSON:

    >>> segmentation = maponyms.main.image_partitioning(im)
    >>> for feat in segmentation['features']:
    ...     print(feat['properties'])

Knowing where to look, we can then pass this image segmentation to the text recognition function, which returns a GeoJSON of all groups of text found within the main map region:

    >>> textcolor = (0,0,0)
    >>> textdata = maponyms.main.text_detection(im, textcolor, seginfo=segmentation)
    >>> len(textdata['features'])
    74

    >>> for feat in textdata['features'][:3]:
    ...     print(feat)
    {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[(76, 40), (254, 40), (254, 62), (76, 62), (76, 40)]]}, 'properties': {'text': 'Burkina Faso', 'text_clean': 'Burkina Faso', 'text_alphas': 'BurkinaFaso', 'conf': 96.304893, 'left': 76, 'top': 40, 'fontheight': 22, 'color': (0, 0, 0), 'color_match': 5.450297095958312, 'width': 178, 'height': 22}}
    {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[(903, 83), (940, 83), (940, 93), (903, 93), (903, 83)]]}, 'properties': {'text': 'Menaka', 'text_clean': 'Menaka', 'text_alphas': 'Menaka', 'conf': 91.843643, 'left': 903, 'top': 83, 'fontheight': 10, 'color': (0, 0, 0), 'color_match': 14.792302518904004, 'width': 37, 'height': 10}}
    {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [[(250, 99), (274, 99), (274, 109), (250, 109), (250, 99)]]}, 'properties': {'text': 'dary', 'text_clean': 'dary', 'text_alphas': 'dary', 'conf': 90.281227, 'left': 250, 'top': 99, 'fontheight': 10, 'color': (0, 0, 0), 'color_match': 16.124256789325415, 'width': 24, 'height': 10}}

After this, based on the resulting GeoJSON of relevant text labels, we try to identify only those that might possibly be toponyms (e.g. that use proper title casing) and try to find their precise location as indicated by a place marker (e.g. a circle or square):

    >>> candidate_toponyms = maponyms.main.toponym_selection(im, textdata, segmentation)
    >>> len(candidate_toponyms['features'])
    49

    >>> for feat in candidate_toponyms['features'][:3]:
    ...     print(feat)
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [945, 96]}, 'properties': {'name': 'Menaka'}}
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [522, 114]}, 'properties': {'name': 'Gossi'}}
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [730, 131]}, 'properties': {'name': 'Ansonge'}}

The final step is trying to find the real-world lat-long coordinate of each toponym. This is done by looking up the names in an SQLite gazetteer database and checking that the relative spatial locations matches up with the coordinates found in the database. The path to the SQLite database is given using the `db` arg (see the installation section for notes about how to get or create the required SQLite gazetteer database):

    >>> db = r"P:\(Temp Backup)\gazetteer data\optim\gazetteers.db"
    >>> matched_toponyms = maponyms.main.match_control_points(candidate_toponyms, db=db)
    >>> len(matched_toponyms['features'])
    40

    >>> for feat in matched_toponyms['features'][:3]:
    ...     print(feat)
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': (-0.86537, 14.22963)}, 'properties': {'origname': 'Aribinda', 'origx': 574, 'origy': 304, 'matchname': 'XAR|Aribinda', 'matchx': -0.86537, 'matchy': 14.22963}}
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': (-3.279831, 9.6586821)}, 'properties': {'origname': 'Varalé', 'origx': 285, 'origy': 854, 'matchname': 'Varalé', 'matchx': -3.279831, 'matchy': 9.6586821}}
    {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': (1.133333, 8.983333)}, 'properties': {'origname': 'Sokode', 'origx': 816, 'origy': 934, 'matchname': 'SOKODE|Sokode|Sokodé|SOKODE|Sokode|Sokodé', 'matchx': 1.133333, 'matchy': 8.983333}

The results of the `match_control_points()` function leaves us with a final GeoJSON representing all toponyms found in the map, along with their pixel position in the image, as well as their location in the real world. 

Alternatively, it's possible to provide any custom geocoder class or object, e.g. `match_control_points(candidate_toponyms, geocoder=some_object)`, as long as this object implements a `some_object.geocode(name)` method. The results of the method must be the same as shown above, i.e. a GeoJSON dict of type FeatureCollection, where the geometries are longitude-latitude points and the properties contain the keys: `origname`, `origx`, `origy`, `matchname`, `matchx`, `matchy`. 

## Using the toponym coordinates to georeference the map

One way these identified map toponyms can be used is to determine the map's coordinate system and georeference it in a way that can be overlaid on other geospatial data. 

To do so, we will leverage the transformio package: 

    >>> import transformio as tio

    >>> # format the control points as expected by transformio
    >>> frompoints = [(feat['properties']['origx'],feat['properties']['origy']) for feat in matched_toponyms['features']]
    >>> topoints = [(feat['properties']['matchx'],feat['properties']['matchy']) for feat in matched_toponyms['features']]
    >>> fromx,fromy = zip(*frompoints)
    >>> tox,toy = zip(*topoints)
    
    >>> # estimate a transform
    >>> trans = tio.transforms.Polynomial(order=3)
    >>> trans.fit(fromx, fromy, tox, toy)
    Polynomial Transform(order=3, estimated=True)

    >>> # warp the image
    >>> warped,affine = tio.imwarp.warp(im, trans)
    >>> warped.save('tests/output/map-georef.png')

![Original image](/tests/output/map-georef.png)

The image has now been georeferenced and the coordinates of the image pixels can be determined from the affine parameters. 


