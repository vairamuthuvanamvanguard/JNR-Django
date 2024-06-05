from django.conf import settings
from django.shortcuts import render
import os
import ee
import fiona
import geemap
import geopandas as gpd
from pyproj import CRS
import rasterio
import numpy as np
from rasterio.mask import mask
from shapely.geometry import mapping
import boto3

def get_s3_presigned_url(bucket_name, object_key, expiration=3600):
    s3_client = boto3.client('s3')
    response = s3_client.generate_presigned_url('get_object',
                                                Params={'Bucket': bucket_name,
                                                        'Key': object_key},
                                                ExpiresIn=expiration)
    return response

def process(request):
    try:
        # Load the precomputed results
        precomputed_path = './precomputed_results/'

        if not os.path.exists(precomputed_path):
            raise FileNotFoundError("Precomputed results not found. Ensure the initialize_ee.py script has been run.")
        
        service_account = 'jnr-670@jnr-master.iam.gserviceaccount.com'
        credentials = ee.ServiceAccountCredentials(service_account, './jnr-master-64eb7abc9c80.json')
        ee.Initialize(credentials)
        
        def_tile_path = os.path.join(precomputed_path, 'application_adjusted_density_v1_clipped.tif')
        project_shapefile_path = os.path.join(precomputed_path, 'VCS1566_UTM.shp')
        shapefile_ee = geemap.shp_to_ee(project_shapefile_path)
        user_shapefile = ee.FeatureCollection(shapefile_ee)

        print("Starting to process the shapefile")

        gdf = gpd.read_file(project_shapefile_path)
        print("Shapefile loaded:", gdf)
        print("Initial CRS:", gdf.crs)
        
        if gdf.crs is None:
            print("Project shapefile has no CRS. Setting to EPSG:4326 as default.")
            gdf.set_crs(epsg=4326, inplace=True)
        
        gdf_new = gdf.to_crs(epsg=32719)
        print("CRS converted to EPSG:32719")
        print("Updated CRS:", gdf_new.crs)

        geometries = [mapping(geom) for geom in gdf_new.geometry if geom is not None and not geom.is_empty]
        print("Number of geometries for masking:", len(geometries))
        
        if not geometries:
            raise ValueError("No valid geometries found for masking.")
        
        geojson_data = gdf_new.to_json()
        print("GeoJSON data generated", geojson_data)

        # Ensure NaNs are handled properly in the mask function
        tile_path = './out/application_adjusted_density_v1.tif'
        clipped_tile_path = './application_adjusted_density_v1_clipped.tif'
        
        # Open the raster file
        with rasterio.open(tile_path) as src:
            # Open the shapefile
            with fiona.open(project_shapefile_path, "r") as shapefile:
                # Get the geometry of the shapefile
                shapefile_geometry = [feature["geometry"] for feature in shapefile]

                # Clip the raster with the shapefile geometry
                clipped_image, clipped_transform = mask(src, shapefile_geometry, crop=True)

                # Get metadata of the clipped raster
                clipped_meta = src.meta.copy()

                # Update metadata with new dimensions, transform, and CRS
                clipped_meta.update({
                    "height": clipped_image.shape[1],
                    "width": clipped_image.shape[2],
                    "transform": clipped_transform,
                    "crs": src.crs
                })
                
        with rasterio.open(clipped_tile_path, 'w', **clipped_meta) as dst:
            dst.write(clipped_image)
            
        agb = ee.ImageCollection('projects/sat-io/open-datasets/ESA/ESA_CCI_AGB')
        jnr_agb = agb.filterBounds(user_shapefile) \
             .filterDate('2019-01-01','2021-01-01') \
             .first().select(['AGB'])
        agb_tile_path = os.path.join(precomputed_path, 'jnr_agb_1566_clipped.tif')
        with rasterio.open(def_tile_path) as src:
            def_array = src.read(1)
            # Ensure NaNs are handled properly
            def_array = np.nan_to_num(def_array, nan=0.0).astype(np.float32)
            print("def_array loaded with shape:", def_array.shape, "and dtype:", def_array.dtype)
            print("Number of NaNs in def_array:", np.isnan(def_array).sum())
            
        tile_path = './jnr_agb_1566.tif'
        clipped_tile_path = './jnr_agb_1566_clipped.tif'
        
        # Open the raster file
        with rasterio.open(tile_path) as src:
            # Open the shapefile
            with fiona.open(project_shapefile_path, "r") as shapefile:
                # Get the geometry of the shapefile
                shapefile_geometry = [feature["geometry"] for feature in shapefile]

                # Clip the raster with the shapefile geometry
                clipped_image, clipped_transform = mask(src, shapefile_geometry, crop=True)

                # Get metadata of the clipped raster
                clipped_meta = src.meta.copy()

                # Update metadata with new dimensions, transform, and CRS
                clipped_meta.update({
                    "height": clipped_image.shape[1],
                    "width": clipped_image.shape[2],
                    "transform": clipped_transform,
                    "crs": src.crs
                })
                
        with rasterio.open(clipped_tile_path, 'w', **clipped_meta) as dst:
            dst.write(clipped_image)
            
        def_tile_path = './application_adjusted_density_v1_clipped.tif'
        with rasterio.open(def_tile_path) as src:
            def_array = src.read(1)
            
        agb_tile_path = './jnr_agb_1566_clipped.tif'
        with rasterio.open(agb_tile_path) as src:
            agb_array = src.read(1)
            
        emission_array = def_array * agb_array
        sum_emission = emission_array.sum()
        total_emission = sum_emission * 1.24 * 0.47 * (44/12)
        print('Total Emission:', total_emission)

        # Upload files to S3
        s3 = boto3.client('s3')
        bucket_name = 'geoproject1'

        s3.upload_file(clipped_tile_path, bucket_name, 'application_adjusted_density_v1_clipped.tif')
        s3.upload_file(agb_tile_path, bucket_name, 'jnr_agb_1566_clipped.tif')

        shapefile_base_name = os.path.splitext(os.path.basename(project_shapefile_path))[0]
        shapefile_files = ['.shp', '.shx', '.dbf', '.prj']
        for extension in shapefile_files:
            s3.upload_file(f"{shapefile_base_name}{extension}", bucket_name, f"{shapefile_base_name}{extension}")

        # Generate pre-signed URLs
        shapefile_url = f'https://geoproject1.s3.ap-south-1.amazonaws.com/VCS1566_UTM.zip'
        raster_url = f'https://geoproject1.s3.ap-south-1.amazonaws.com/application_adjusted_density_v1_clipped.tif'
        
        # Render the URLs in the template
        return render(request, 'process.html', {
            'total_emission': total_emission,
            'shapefile_url': shapefile_url,
            'raster_url': raster_url
        })

    except Exception as e:
        return render(request, 'error.html', {'error': str(e)})
