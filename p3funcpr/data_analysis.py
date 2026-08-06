import pandas as pd
import numpy as np


def analyze_diets(file_path):

    # Load dataset
    df = pd.read_csv(file_path)


    # -------------------------
    # Data Cleaning
    # -------------------------

    numeric_columns = [
        "Protein(g)",
        "Carbs(g)",
        "Fat(g)"
    ]

    for col in numeric_columns:
        df[col] = df[col].fillna(df[col].mean())


    # -------------------------
    # Analysis 1:
    # Average Macronutrients
    # -------------------------

    avg_macros = (
        df.groupby("Diet_type")
        [
            "Protein(g)",
            "Carbs(g)",
            "Fat(g)"
        ]
        .mean()
        .reset_index()
    )


    # -------------------------
    # Analysis 2:
    # Highest Protein Diet
    # -------------------------

    highest_protein = (
        avg_macros
        .loc[
            avg_macros["Protein(g)"].idxmax()
        ]
    )


    # -------------------------
    # Analysis 3:
    # Common Cuisine
    # -------------------------

    common_cuisine = (
        df.groupby("Diet_type")
        ["Cuisine_type"]
        .agg(
            lambda x:
            x.mode()[0]
            if len(x.mode()) > 0
            else "Unknown"
        )
        .reset_index()
    )


    # -------------------------
    # Create response object
    # -------------------------

    result = {

        "total_records": len(df),

        "average_macronutrients":
            avg_macros.to_dict(
                orient="records"
            ),

        "highest_protein_diet": {

            "diet":
                highest_protein["Diet_type"],

            "protein":
                round(
                    highest_protein["Protein(g)"],
                    2
                )
        },


        "common_cuisines":
            common_cuisine.to_dict(
                orient="records"
            )
    }


    return result