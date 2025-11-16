"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# News app schemas

class Source(BaseModel):
    name: str = Field(..., description="Human-friendly source name, e.g., Reuters")
    slug: str = Field(..., description="Unique slug id, e.g., reuters")
    url: HttpUrl = Field(..., description="Homepage URL")
    rss_url: HttpUrl = Field(..., description="RSS feed URL")
    category: Optional[str] = Field(None, description="Category or region")
    reliability: Optional[int] = Field(100, ge=0, le=100, description="Editorial reliability score")

class Article(BaseModel):
    source_slug: str = Field(..., description="Slug of the source")
    source_name: str = Field(..., description="Display name of the source")
    title: str = Field(..., description="Article title")
    summary: Optional[str] = Field(None, description="Short summary/description")
    link: HttpUrl = Field(..., description="Canonical link to original article")
    image_url: Optional[str] = Field(None, description="Image URL if available")
    published_at: Optional[datetime] = Field(None, description="Published timestamp if provided")
    categories: Optional[List[str]] = Field(default_factory=list)

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
