import azure.functions as func
from azure.storage.blob import BlobServiceClient
import redis
import io
import os
import pandas as pd
import json
from azure.cosmos import CosmosClient
import bcrypt


app = func.FunctionApp(
    http_auth_level=func.AuthLevel.ANONYMOUS
)

def get_user_container():

    client = CosmosClient(
        os.environ["COSMOS_ENDPOINT"],
        credential=os.environ["COSMOS_KEY"]
    )

    database = client.get_database_client(
        os.environ["COSMOS_DATABASE"]
    )

    return database.get_container_client(
        os.environ["COSMOS_CONTAINER"]
    )

# Redis connection

def get_redis_client():

    return redis.Redis.from_url(
        os.environ["REDIS_CONNECTION_STRING"],
        decode_responses=True
    )

# Blob Trigger

@app.blob_trigger(
    arg_name="myblob",
    path="datasets/All_Diets.csv",
    connection="AzureWebJobsStorage"
)
def clean_dataset(myblob: func.InputStream):

    # 1. Read CSV

    blob_data = myblob.read()

    df = pd.read_csv(
        io.BytesIO(blob_data)
    )


    # 2. Clean data

    numeric_columns = [
        "Protein(g)",
        "Carbs(g)",
        "Fat(g)"
    ]

    for col in numeric_columns:
        df[col] = df[col].fillna(
            df[col].mean()
        )


    clean_csv = df.to_csv(
        index=False
    )


    # 3. Save Clean_Diets.csv

    connection_string = os.environ[
        "AzureWebJobsStorage"
    ]

    blob_service_client = (
        BlobServiceClient
        .from_connection_string(
            connection_string
        )
    )


    processed_container = (
        blob_service_client
        .get_container_client(
            "processed"
        )
    )


    processed_blob = (
        processed_container
        .get_blob_client(
            "Clean_Diets.csv"
        )
    )


    processed_blob.upload_blob(
        clean_csv,
        overwrite=True
    )


    # 4. Calculate chart data

    avg_macros = (
        df.groupby("Diet_type")
        [
            [
                "Protein(g)",
                "Carbs(g)",
                "Fat(g)"
            ]
        ]
        .mean()
        .reset_index()
    )


    diet_distribution = (
        df["Diet_type"]
        .value_counts()
        .reset_index()
    )


    diet_distribution.columns = [
        "Diet_type",
        "Count"
    ]


    scatter = df[
        [
            "Protein(g)",
            "Carbs(g)",
            "Diet_type"
        ]
    ].head(100)


    heatmap = (
        df.groupby("Diet_type")
        [
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


    cache_result = {

    "records_processed": int(len(df)),

    "nutrition_data":
        avg_macros.round(2)
        .to_dict(
            orient="records"
        ),

    "diet_distribution":
        diet_distribution
        .to_dict(
            orient="records"
        ),

    "scatter_data":
        scatter
        .to_dict(
            orient="records"
        ),

    "heatmap_data":
        heatmap
    }


    # 5. Store in Redis

    print("Connecting to Redis")

    redis_client = get_redis_client()

    redis_client.ping()

    print("Redis connection successful")

    redis_client.set(
        "nutrition_cache",
        json.dumps(
            cache_result,
            default=float
        )
    )

    print("Redis cache updated")



# HTTP API

@app.route(
    route="register",
    methods=["POST"]
)
def register(req: func.HttpRequest):

    try:
        body=req.get_json()
    except:
        return func.HttpResponse(
            "Invalid JSON",
            status_code=400
    )

    email = body["email"]
    username = body["username"]
    password = body["password"]

    container = get_user_container()

    users = list(
        container.query_items(
            query=
            "SELECT * FROM c WHERE c.email=@email",
            parameters=[
                {
                    "name":"@email",
                    "value":email
                }
            ],
            enable_cross_partition_query=True
        )
    )

    if users:

        return func.HttpResponse(
            "User already exists",
            status_code=409
        )

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    user = {

        "id": email,

        "email": email,

        "username": username,

        "password_hash": password_hash
    }

    container.create_item(user)

    return func.HttpResponse(
        "User registered",
        status_code=201
    )
    
@app.route(
route="login",
methods=["POST"]
)
def login(req: func.HttpRequest):

    body = req.get_json()

    email = body["email"]
    password = body["password"]

    container = get_user_container()

    users = list(
        container.query_items(
            query=
            "SELECT * FROM c WHERE c.email=@email",
            parameters=[
                {
                    "name":"@email",
                    "value":email
                }
            ],
            enable_cross_partition_query=True
        )
    )

    if not users:

        return func.HttpResponse(
            "Invalid login",
            status_code=401
        )

    user = users[0]

    valid = bcrypt.checkpw(
        password.encode("utf-8"),
        user["password_hash"].encode("utf-8")
    )

    if not valid:

        return func.HttpResponse(
            "Invalid login",
            status_code=401
        )

    return func.HttpResponse(
        json.dumps({
            "authenticated": True,
            "username": user["username"]
        }),
        mimetype="application/json"
    )

@app.route(
    route="nutrition",
    methods=["GET"]
)
def nutrition(req: func.HttpRequest):

    redis_client = get_redis_client()

    cached_data = redis_client.get(
        "nutrition_cache"
    )


    if cached_data is None:

        return func.HttpResponse(
            "Cache unavailable",
            status_code=503
        )


    return func.HttpResponse(
        cached_data,
        mimetype="application/json"
    )
    
@app.route(
route="recipes",
methods=["GET"]
)
def recipes(req: func.HttpRequest):

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


    # Get query parameters

    diet = req.params.get("diet")
    keyword = req.params.get("keyword")


    # Filter by diet type

    if diet and diet.lower() != "all":

        df = df[
            df["Diet_type"]
            .str.lower()
            ==
            diet.lower()
        ]


    # Search recipe name

    if keyword:

        df = df[
            df["Recipe_name"]
            .str.contains(
                keyword,
                case=False,
                na=False
            )
        ]


    # Pagination

    page = int(
        req.params.get(
            "page",
            1
        )
    )


    page_size = int(
        req.params.get(
            "page_size",
            10
        )
    )


    start = (page - 1) * page_size

    end = start + page_size


    results = df.iloc[start:end]


    response = {

        "page": page,

        "page_size": page_size,

        "total_results": len(df),

        "recipes":
            results.to_dict(
                orient="records"
            )

    }


    return func.HttpResponse(
        json.dumps(
            response,
            default=str
        ),
        mimetype="application/json"
    )