import ee
import geemap
import geopandas as gpd
from pyproj import CRS
import os
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping
import boto3

def initialize_earth_engine():
    service_account = 'jnr-670@jnr-master.iam.gserviceaccount.com'
    credentials = ee.ServiceAccountCredentials(service_account, './jnr-master-64eb7abc9c80.json')
    ee.Initialize(credentials)

    project_shapefile_path = './VCS1566_UTM.shp'
    shapefile_ee = geemap.shp_to_ee(project_shapefile_path)

    # Load the shapefile
    gdf = gpd.read_file(project_shapefile_path)
    # Extract the CRS from the GeoDataFrame
    crs = gdf.crs

    if crs is None:
        print("CRS is None, setting default CRS to EPSG:4326")
        crs = CRS.from_epsg(4326)
        gdf.set_crs(crs, inplace=True)
    else:
        print("Shapefile CRS:", crs)

    # Get the EPSG code
    epsg_code = crs.to_epsg()
    formatted_epsg_code = f"EPSG:{epsg_code}"
    print("Shapefile EPSG code:", formatted_epsg_code)

    # Load the FAO level 1 boundary data
    fao_boundaries = ee.FeatureCollection('FAO/GAUL/2015/level1')
    fao_l2_boundaries = ee.FeatureCollection('FAO/GAUL/2015/level2')

    # Load your shapefile as an EE feature collection
    user_shapefile = ee.FeatureCollection(shapefile_ee)
    buffered_shapefile = user_shapefile.map(lambda feature: feature.buffer(-1000))
    # Clip FAO level 1 boundaries using the buffered shapefile
    overlapping_boundaries = fao_boundaries.filterBounds(buffered_shapefile.geometry())
    buffered_l2_shapefile = overlapping_boundaries.map(lambda feature: feature.buffer(-1000))
    overlapping_l2_boundaries = fao_l2_boundaries.filterBounds(buffered_l2_shapefile.geometry())

    # Merge overlapping boundaries into a single boundary
    merged_boundary = ee.FeatureCollection(overlapping_boundaries.geometry().dissolve())

    # Reproject function
    def reproject_geometry(feature):
        geometry = feature.geometry()
        reprojected_geometry = geometry.transform(formatted_epsg_code, 30)
        return feature.setGeometry(reprojected_geometry)

    reprojected_boundary = overlapping_boundaries.map(reproject_geometry)
    reprojected_l2_boundary = overlapping_l2_boundaries.map(reproject_geometry)

    # Save the boundaries locally
    boundaries_dir = './precomputed_results'
    if not os.path.exists(boundaries_dir):
        os.makedirs(boundaries_dir)

    boundary_path = os.path.join(boundaries_dir, 'vichada_boundary1566.shp')
    l2_boundary_path = os.path.join(boundaries_dir, 'vichada_l2_boundary1566.shp')
    geemap.ee_export_vector(reprojected_boundary, filename=boundary_path)
    geemap.ee_export_vector(reprojected_l2_boundary, filename=l2_boundary_path)
    print("Boundaries exported locally")

    # Process Hansen map
    gfc = ee.Image("UMD/hansen/global_forest_change_2022_v1_10").clip(overlapping_boundaries)
    treecover = gfc.select(["treecover2000"])
    lossyear = gfc.select(["lossyear"])
    forest2000 = treecover.gte(10).toByte()
    loss01_14 = lossyear.gte(1).And(lossyear.lte(14))
    loss01_18 = lossyear.gte(1).And(lossyear.lte(18))
    loss01_22 = lossyear.gte(1).And(lossyear.lte(22))
    forest2015 = forest2000.where(loss01_14.eq(1), 0)
    forest2019 = forest2000.where(loss01_18.eq(1), 0)
    forest2023 = forest2000.where(loss01_22.eq(1), 0)

    def categorize_changes(image1, image2, image3):
        condition1 = image1.eq(1).And(image2.eq(0)).And(image3.eq(0))
        condition2 = image1.eq(1).And(image2.eq(1)).And(image3.eq(0))
        condition3 = image1.eq(1).And(image2.eq(1)).And(image3.eq(1))
        new_image = ee.Image(0).where(condition1, 1).where(condition2, 2).where(condition3, 3)
        new_image = new_image.where(new_image.eq(0), 0)
        return new_image

    change_raster_hansen = categorize_changes(forest2015, forest2019, forest2023)

    # Export Hansen change raster
    lct_1566_hansen_path = os.path.join(boundaries_dir, 'lct_1566_hansen.tif')
    geemap.ee_export_image(change_raster_hansen, filename=lct_1566_hansen_path, scale=30, crs='EPSG:32719', region=overlapping_boundaries.geometry().bounds().getInfo()['coordinates'])
    print("Hansen change raster exported locally")

    # Upload files to S3
    s3 = boto3.client('s3')
    bucket_name = 'geoproject1'

    s3.upload_file(boundary_path, bucket_name, 'vichada_boundary1566.shp')
    s3.upload_file(l2_boundary_path, bucket_name, 'vichada_l2_boundary1566.shp')
    s3.upload_file(lct_1566_hansen_path, bucket_name, 'lct_1566_hansen.tif')
    print("Files uploaded to S3")

if __name__ == "__main__":
    initialize_earth_engine()
