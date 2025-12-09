from fastapi import FastAPI, Query
import snscrape.modules.twitter as sntwitter

app = FastAPI()

@app.get("/scrape")
def scrape(
    query: str = Query(..., description="Twitter search query"),
    limit: int = 50
):
    tweets = []

    for i, tweet in enumerate(sntwitter.TwitterSearchScraper(query).get_items()):
        if i >= limit:
            break

        tweets.append({
            "tweet_id": tweet.id,
            "tweet_text": tweet.content,
            "created_at": tweet.date,
            "tweet_url": tweet.url,
            "metrics": {
                "likes": tweet.likeCount,
                "retweets": tweet.retweetCount,
                "replies": tweet.replyCount,
                "quotes": tweet.quoteCount
            },
            "user": {
                "username": tweet.user.username,
                "name": tweet.user.displayname,
                "verified": tweet.user.verified,
                "followers": tweet.user.followersCount,
                "created_at": tweet.user.created,
                "description": tweet.user.description
            }
        })

    return {
        "count": len(tweets),
        "tweets": tweets
    }
