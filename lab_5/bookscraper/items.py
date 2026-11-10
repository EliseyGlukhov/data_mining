# bookscraper/items.py
import scrapy

class BookItem(scrapy.Item):
    upc = scrapy.Field()
    title = scrapy.Field()
    category = scrapy.Field()
    product_type = scrapy.Field()

    price_excl_tax = scrapy.Field()
    price_incl_tax = scrapy.Field()
    tax = scrapy.Field()
    availability = scrapy.Field()
    number_of_reviews = scrapy.Field()

    description = scrapy.Field()
    rating = scrapy.Field()
    image_url = scrapy.Field()
    product_url = scrapy.Field()