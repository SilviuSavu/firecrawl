import os
import json
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")


app = FirecrawlApp(api_key=firecrawl_api_key)
client = OpenAI(api_key=openai_api_key)

def main():
    
    blog_url = input("Enter the blog URL: ")

    if not blog_url.strip():
        blog_url = "https://www.firecrawl.dev/blog/how-to-use-openai-o1-reasoning-models-in-applications"

    
    print("Scraping the blog content...")
    blog_scrape_result = app.scrape_url(blog_url, params={'formats': ['markdown']})

    
    blog_content = blog_scrape_result.get('markdown', '')

    
    top_level_domain = '/'.join(blog_url.split('/')[:3])

    
    print("Mapping the website to get all links...")
    site_map = app.map_url(top_level_domain)

    
    site_links = site_map.get('links', [])


    prompt = f"""
You are an AI assistant helping to improve a blog post.

Here is the original blog post content:

{blog_content}

Here is a list of other pages on the website:

{json.dumps(site_links, indent=2)}

Please revise the blog post to include internal links to some of these pages where appropriate. Make sure the internal links are relevant and enhance the content.

Only return the revised blog post in markdown format.
"""

    import re

    
    def count_links(markdown_content):
        return len(re.findall(r'\[.*?\]\(.*?\)', markdown_content))

    
    print("Generating the revised blog post with internal links...")
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        prediction={
            "type": "content",
            "content": blog_content
        }
    );

    revised_blog_post = completion.choices[0].message.content

    
    original_links_count = count_links(blog_content)
    revised_links_count = count_links(revised_blog_post)

    
    print("\nRevised blog post (first 500 characters):")
    print(revised_blog_post[:500])
    print(f"\nNumber of links in the original blog post: {original_links_count}")
    print(f"Number of links in the revised blog post: {revised_links_count}")

if __name__ == "__main__":
    main()
