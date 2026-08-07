import azure.functions as func
from azure.storage.blob import BlobServiceClient
import io
import os
import pandas as pd
import json
import time
from datetime import datetime


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.blob_trigger(
    arg_name="myblob",
    path="datasets/All_Diets.csv",
    connection="AzureWebJobsStorage"
)
def clean_dataset(myblob: func.InputStream):
# Cleaning
    print("CSV Updated.")
    
    df = pd.read_csv(myblob)
    
    numeric_columns = [
        "Protein(g)",
        "Carbs(g)",
        "Fat(g)"
    ]
    
    for col in numeric_columns:
        df[col] = df[col].fillna(df[col].mean())
        
    clean_csv = df.to_csv(index=False)
    
    
    connection_string = os.environ["AzureWebJobsStorage"]

    blob_service_client = BlobServiceClient.from_connection_string(
        connection_string
    )


    processed_container = (
        blob_service_client.get_container_client(
            "processed"
        )
    )

    processed_blob = (
        processed_container.get_blob_client(
            "Clean_Diets.csv"
        )
    )

    processed_blob.upload_blob(
        clean_csv,
        overwrite=True
    )

@app.route(
    route="nutrition",
    methods=["GET"]
)
def nutrition(req: func.HttpRequest) -> func.HttpResponse:

    start = time.time()

    connection_string = os.environ["AzureWebJobsStorage"]

    blob_service_client = BlobServiceClient.from_connection_string(
        connection_string
    )


    container_client = blob_service_client.get_container_client(
        "processed"
    )


    blob_client = container_client.get_blob_client(
        "Clean_Diets.csv"
    )


    blob_data = blob_client.download_blob().readall()


    df = pd.read_csv(
        io.BytesIO(blob_data)
    )


    # ----------------------
    # Bar Chart Data
    # ----------------------

    avg_macros = (
    df.groupby("Diet_type")[
        [
            "Protein(g)",
            "Carbs(g)",
            "Fat(g)"
        ]
    ]
    .mean()
    .reset_index()
)


    # ----------------------
    # Pie Chart Data
    # ----------------------

    diet_distribution = (
        df["Diet_type"]
        .value_counts()
        .reset_index()
    )

    diet_distribution.columns = [
        "Diet_type",
        "Count"
    ]


    # ----------------------
    # Scatter Plot Data
    # ----------------------

    scatter = df[
        [
            "Protein(g)",
            "Carbs(g)",
            "Diet_type"
        ]
    ].head(100)


    # ----------------------
    # Heatmap Data
    # ----------------------

    heatmap = (
        df.groupby("Diet_type")[
            [
                "Protein(g)",
                "Carbs(g)",
                "Fat(g)"
            ]
        ]
        .mean()
        .round(2)
        .to_dict()
    )


    result = {

        "execution_time":
        str(datetime.now()),

        "records_processed":
        len(df),

        "nutrition_data":
        avg_macros.to_dict(
            orient="records"
        ),

        "diet_distribution":
        diet_distribution.to_dict(
            orient="records"
        ),

        "scatter_data":
        scatter.to_dict(
            orient="records"
        ),

        "heatmap_data":
        heatmap
    }


    return func.HttpResponse(
        json.dumps(result),
        mimetype="application/json"
    )
    
