from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from uuid import UUID

from pydantic import AnyUrl, BaseModel, Field, FileUrl, validator

from datalad_registry.utils import StrEnum

from ..url_metadata.models import URLMetadataModel


def path_url_must_be_absolute(url):
    """
    Validator for the path URL field that ensures that the URL is absolute
    """
    if isinstance(url, Path) and not url.is_absolute():
        raise ValueError("Path URLs must be absolute")
    return url


class MetadataReturnOption(StrEnum):
    """
    Enum for representing the metadata return options
    """

    references = "references"
    content = "content"


class PathParams(BaseModel):
    """
    Pydantic model for representing the path parameters for API endpoints related to
    dataset URLs.
    """

    id: int = Field(..., description="The ID of the dataset URL")


class QueryParams(BaseModel):
    """
    Pydantic model for representing the query parameters to query
    the dataset_urls endpoint
    """

    url: Optional[Union[FileUrl, AnyUrl, Path]] = Field(None, description="The URL")

    ds_id: Optional[UUID] = Field(None, description="The ID, a UUID, of the dataset")

    min_annex_key_count: Optional[int] = Field(
        None, description="The minimum number of annex keys "
    )
    max_annex_key_count: Optional[int] = Field(
        None, description="The maximum number of annex keys "
    )

    min_annexed_files_in_wt_count: Optional[int] = Field(
        None, description="The minimum number of annexed files in the working tree"
    )
    max_annexed_files_in_wt_count: Optional[int] = Field(
        None, description="The maximum number of annexed files in the working tree"
    )

    min_annexed_files_in_wt_size: Optional[int] = Field(
        None,
        description="The minimum size of annexed files in the working tree in bytes",
    )
    max_annexed_files_in_wt_size: Optional[int] = Field(
        None,
        description="The maximum size of annexed files in the working tree in bytes",
    )

    earliest_last_update: Optional[datetime] = Field(
        None,
        description="The earliest last update time",
    )
    latest_last_update: Optional[datetime] = Field(
        None,
        description="The latest last update time",
    )

    min_git_objects_kb: Optional[int] = Field(
        None, description="The minimum size of the `.git/objects` in KiB"
    )
    max_git_objects_kb: Optional[int] = Field(
        None, description="The maximum size of the `.git/objects` in KiB"
    )

    processed: Optional[bool] = Field(
        None,
        description="Whether an initial processing has been completed "
        "on the dataset URL",
    )

    cache_path: Optional[Path] = Field(
        None,
        description="The path, relative or full, of the cached clone of the dataset at "
        "the URL in the local file system, the file system of the "
        "Celery worker. If the path is relative, it is relative to the base cache path."
        " If the path is full, only the last three components of the path are used "
        "in the query.",
    )

    return_metadata: Optional[MetadataReturnOption] = Field(
        None,
        # todo: description to be modified
        description="Whether and how to return metadata of the datasets at the URLs. "
        "If this query parameter is not provided, the `metadata` field "
        "of each returned dataset URL object will be `null`. "
        'If this query parameter is "references", '
        "the `metadata` field of each returned dataset URL object will be "
        "an object with metadata extractor names being the fields and "
        "the links to the corresponding metadata being the values. "
        'If this query parameter is "content", the `metadata` field '
        "of each returned dataset URL object will be an object "
        "with metadata extractor names being the fields "
        "and objects representing the corresponding metadata "
        "being the values.",
    )

    # Validator
    _path_url_must_be_absolute = validator("url", allow_reuse=True)(
        path_url_must_be_absolute
    )


class DatasetURLSubmitModel(BaseModel):
    """
    Model for representing the database model URL for submission communication
    """

    url: Union[FileUrl, AnyUrl, Path] = Field(..., description="The URL")

    # Validator
    _path_url_must_be_absolute = validator("url", allow_reuse=True)(
        path_url_must_be_absolute
    )


class DatasetURLRespBaseModel(DatasetURLSubmitModel):
    """
    Base model for `DatasetURLRespModel`

    All fields defined in this model are intended to be populated
    from an orm model object directly.
    """

    id: int = Field(..., description="The ID of the dataset URL")
    ds_id: Optional[UUID] = Field(
        ..., alias="ds_id", description="The ID, a UUID, of the dataset"
    )
    describe: Optional[str] = Field(
        ...,
        alias="head_describe",
        description="The output of `git describe --tags --always` on the dataset",
    )
    annex_key_count: Optional[int] = Field(..., description="The number of annex keys")
    annexed_files_in_wt_count: Optional[int] = Field(
        ..., description="The number of annexed files in the working tree"
    )
    annexed_files_in_wt_size: Optional[int] = Field(
        ..., description="The size of annexed files in the working tree in bytes"
    )
    last_update: Optional[datetime] = Field(
        ...,
        alias="info_ts",
        description="The last time the local copy of the dataset was updated",
    )
    git_objects_kb: Optional[int] = Field(
        ..., description="The size of the `.git/objects` in KiB"
    )
    processed: bool = Field(
        description="Whether an initial processing has been completed "
        "on the dataset URL"
    )

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class DatasetURLRespModel(DatasetURLRespBaseModel):
    """
    Model for representing the database model URL in response communication
    """

    metadata: Optional[list[URLMetadataModel]] = Field(
        ..., alias="metadata_", description="The metadata of the dataset at the URL"
    )


class DatasetURLs(BaseModel):
    """
    Model for representing a list of dataset URLs in response communication
    """

    __root__: list[DatasetURLRespModel]

    class Config:
        orm_mode = True
