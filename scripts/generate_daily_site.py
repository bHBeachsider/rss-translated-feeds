"""
Generate daily static site from translated RSS feeds
Creates HTML pages, JSON summaries, and audio briefs
"""

import os
import json
import feedparser
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class DailySiteGenerator:
    def __init__(self, feeds_dir: str, output_dir: str):
        self.feeds_dir = Path(feeds_dir)
        self.output_dir = Path(output_dir)
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Country/topic mappings
        self.country_keywords = {
            "cuba": ["cuba", "cuban", "havana", "granma"],
            "venezuela": ["venezuela", "venezuelan", "caracas", "pdvsa", "maduro"],
            "haiti": ["haiti", "haitian", "port-au-prince"],
            "dr": ["dominican", "santo domingo", "diario libre"]
        }
    
    def collect_stories(self) -> Dict[str, List[Dict]]:
        """Collect all stories from feeds, categorized by country"""
        stories = defaultdict(list)
        
        for feed_file in self.feeds_dir.glob("*.en.xml"):
            try:
                feed = feedparser.parse(str(feed_file))
                
                for entry in feed.entries:
                    story = {
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", "")[:500],  # Limit summary length
                        "published": entry.get("published", ""),
                        "source": feed.feed.get("title", ""),
                    }
                    
                    # Categorize by country
                    for country, keywords in self.country_keywords.items():
                        if any(kw in story["title"].lower() or kw in story["summary"].lower() 
                               for kw in keywords):
                            stories[country].append(story)
                    
                    # Always add to "caribbean" (general)
                    stories["caribbean"].append(story)
                    
            except Exception as e:
                print(f"Error parsing {feed_file}: {e}")
        
        return stories
    
    def generate_summary(self, stories: List[Dict], country: str) -> str:
        """Use OpenAI to generate a summary of the day's stories"""
        if not stories:
            return f"No significant news from {country.title()} today."
        
        # Prepare story text (limit to top 15 stories)
        story_text = "\n\n".join([
            f"**{s['title']}**\n{s['summary']}"
            for s in stories[:15]
        ])
        
        prompt = f"""You are a geopolitical analyst specializing in Caribbean affairs.

Summarize today's key developments in {country.upper()} based on these news stories:

{story_text}

Provide:
1. A 2-3 sentence executive summary
2. 3-5 key bullet points of the most important developments
3. Brief analysis of implications

Keep it factual and concise."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Summary generation failed: {e}"
    
    def generate_audio_brief(self, summary_text: str, country: str) -> str:
        """Generate audio brief using OpenAI TTS"""
        audio_file = self.output_dir / "audio" / f"{self.today}-{country}.mp3"
        audio_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            response = self.client.audio.speech.create(
                model="tts-1",
                voice="nova",
                input=f"{country.upper()} Intelligence Brief for {self.today}.\n\n{summary_text}"
            )
            with open(audio_file, "wb") as f:`n                f.write(response.content)
            return f"audio/{self.today}-{country}.mp3"
        except Exception as e:
            print(f"Error generating audio: {e}")
            return None
    
    def create_html_page(self, country: str, stories: List[Dict], summary: str, audio_path: str = None):
        """Generate HTML page for a country"""
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{country.upper()} Intelligence Brief - {self.today}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.6;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .summary {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            white-space: pre-wrap;
        }}
        .story {{
            background: white;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .story h3 {{
            margin-top: 0;
            color: #333;
        }}
        .story a {{
            color: #667eea;
            text-decoration: none;
        }}
        .story a:hover {{
            text-decoration: underline;
        }}
        .meta {{
            color: #666;
            font-size: 0.9em;
            margin-top: 10px;
        }}
        audio {{
            width: 100%;
            margin: 20px 0;
        }}
        .nav {{
            margin: 20px 0;
        }}
        .nav a {{
            margin-right: 15px;
            color: white;
            text-decoration: none;
            padding: 5px 10px;
            background: rgba(255,255,255,0.2);
            border-radius: 5px;
        }}
        .nav a:hover {{
            background: rgba(255,255,255,0.3);
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1> {country.upper()} Intelligence Brief</h1>
        <p> {self.today} | {len(stories)} stories</p>
        <div class="nav">
            <a href="../.."> Home</a>
            <a href="../../countries/cuba">Cuba</a>
            <a href="../../countries/venezuela">Venezuela</a>
            <a href="../../countries/haiti">Haiti</a>
            <a href="../../countries/dr">Dominican Republic</a>
        </div>
    </div>
    
    <div class="summary">
        <h2> Executive Summary</h2>
        {f'<audio controls><source src="../../{audio_path}" type="audio/mpeg"></audio>' if audio_path else ''}
        <div>{summary}</div>
    </div>
    
    <h2> Today's Stories ({len(stories)})</h2>
"""
        
        for story in stories[:30]:  # Limit to 30 stories
            html += f"""
    <div class="story">
        <h3><a href="{story['link']}" target="_blank">{story['title']}</a></h3>
        <p>{story['summary']}</p>
        <div class="meta">
             {story['source']}
        </div>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        # Save HTML
        if country == "caribbean":
            html_path = self.output_dir / "index.html"
        else:
            html_path = self.output_dir / "countries" / country / "index.html"
        
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        print(f" Created {html_path}")
    
    def save_json(self, country: str, stories: List[Dict], summary: str):
        """Save JSON data file"""
        json_path = self.output_dir / "daily" / self.today / f"{country}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "date": self.today,
            "country": country,
            "summary": summary,
            "story_count": len(stories),
            "stories": stories[:30]  # Limit stories in JSON
        }
        
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f" Created {json_path}")
    
    def generate(self):
        """Main generation process"""
        print(f" Generating daily site for {self.today}...")
        
        # Collect stories
        print(" Collecting stories from feeds...")
        stories_by_country = self.collect_stories()
        
        for country, stories in stories_by_country.items():
            if not stories:
                continue
            
            print(f"\n Processing {country.upper()} ({len(stories)} stories)...")
            
            # Generate summary
            print("   Generating AI summary...")
            summary = self.generate_summary(stories, country)
            
            # Generate audio (only for main regions to save API costs)
            audio_path = None
            if country in ["caribbean", "cuba"]:
                print("   Generating audio brief...")
                audio_path = self.generate_audio_brief(summary, country)
            
            # Create HTML page
            self.create_html_page(country, stories, summary, audio_path)
            
            # Save JSON
            self.save_json(country, stories, summary)
        
        print(f"\n Site generation complete! Output: {self.output_dir}")
        print(f"   Open: {self.output_dir}/index.html")

def main():
    generator = DailySiteGenerator(
        feeds_dir="output/feeds",
        output_dir="site"
    )
    generator.generate()

if __name__ == "__main__":
    main()
