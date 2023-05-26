# This file is for defining the API endpoints related to dataset URL metadata,
# i.e. the metadata of datasets at individual URLs.

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field, StrictStr

from datalad_registry.models import URLMetadata, db

from .. import API_URL_PREFIX, COMMON_API_RESPONSES

bp = APIBlueprint(
    "url_metadata_api",
    __name__,
    url_prefix=f"{API_URL_PREFIX}/url-metadata",
    abp_tags=[Tag(name="URL Metadata", description="API endpoints for URL metadata")],
    abp_responses=COMMON_API_RESPONSES,
)


class PathParams(BaseModel):
    """
    Pydantic model for representing the path parameters for the URL metadata API
    endpoints.
    """

    url_metadata_id: int = Field(..., description="The ID of the URL metadata")


class URLMetadataModel(BaseModel):
    """
    Model for representing the database model URLMetadata for communication
    """

    dataset_describe: StrictStr
    dataset_version: StrictStr
    extractor_name: StrictStr
    extractor_version: StrictStr
    extraction_parameter: dict
    extracted_metadata: dict

    class Config:
        orm_mode = True


@bp.get("/<int:url_metadata_id>", responses={"200": URLMetadataModel})
def url_metadata(path: PathParams):
    """
    Get URL metadata by ID.
    """
    data = URLMetadataModel.from_orm(db.get_or_404(URLMetadata, path.url_metadata_id))
    return data.dict()
