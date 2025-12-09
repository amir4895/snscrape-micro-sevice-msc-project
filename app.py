from fastapi import FastAPI, Query
import time
import logging
from datetime import datetime

# ------------------------------------------------------------------
# Logging (goes to Render logs)
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("snscrape-service")

# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------
app = FastAPI(title="snscrape microservice", version="1.0")

# ------------------------------------------------------------------
# Health check (never touches snscrape)
# ------------------------------------------------------------------
@app.get("/health")
def health():
    logger.info("Health check called")
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat()
    }

# ------------------------------------------------------------------
# Internal helper – isolated snscrape
# ------------------------------------------------------------------
def scrape_with_backoff(query: str, limit: int, max_attempts: int = 3):
    """
    Best-effort Twitter scrape.
    Never raises – always returns (tweets, error_string_or_None).
    """

    try:
        # IMPORT snscrape ONLY HERE (critical!)
        import snscrape.modules.twitter as sntwitter
        from snscrape.base import ScraperException
    except Exception as e:
        logger.error(f"snscrape import failed: {e}")
        return [], f"snscrape_import_failed: {e}"

    logger.info(f"Starting scrape | query='{query}' | limit={limit}")

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Scrape attempt {attempt}/{max_attempts}")
            tweets = []

            scraper = sntwitter.TwitterSearchScraper(query)

            for i, tweet in enumerate(scraper.get_items()):
                if i >= limit:
                    break

                tweets.append({
                    "tweet_id": tweet.id,
                    "text": tweet.content,
                    "url": tweet.url,
                    "created_at": tweet.date.isoformat(),
                    "metrics": {
                        "likes": tweet.likeCount,
                        "retweets": tweet.retweetCount,
                        "replies": tweet.replyCount,
                        "quotes": tweet.quoteCount
                    },
                    "user": {
                        "username": tweet.user.username,
                        "verified": tweet.user.verified,
                        "followers": tweet.user.followersCount,
                        "account_created": (
                            tweet.user.created.isoformat()
                            if tweet.user.created else None
                        )
                    }
                })

                logger.info(
                    f"Fetched tweet {i+1}/{limit} | "
                    f"id={tweet.id} | user=@{tweet.user.username}"
                )

                # IMPORTANT: throttle to avoid blocking
                time.sleep(1.5)

            logger.info(f"Scrape successful | returned {len(tweets)} tweets")
            return tweets, None

        except ScraperException as e:
            backoff = attempt * 10
            logger.warning(
                f"ScraperException attempt {attempt}: {e} | backoff {backoff}s"
            )
            time.sleep(backoff)

        except Exception as e:
            logger.error("Unexpected scrape error", exc_info=True)
            return [], f"unexpected_error: {e}"

    logger.error("All scrape attempts failed (rate-limited/block)")
    return [], "rate_limited_or_blocked"

# ------------------------------------------------------------------
# Public scrape endpoint (n8n will call this)
# ------------------------------------------------------------------
@app.get("/scrape")
def scrape(
    query: str = Query(..., description="Twitter search query"),
    limit: int = Query(5, ge=1, le=20)
):
    logger.info(f"/scrape called | query='{query}' | limit={limit}")

    start = time.time()
    tweets, error = scrape_with_backoff(query, limit)
    duration = round(time.time() - start, 2)

    response = {
        "query": query,
        "requested_limit": limit,
        "returned_count": len(tweets),
        "duration_seconds": duration,
        "status": "ok" if error is None else "partial_or_failed",
        "tweets": tweets,
        "timestamp": datetime.utcnow().isoformat()
    }

    if error:
        response["error"] = error
        logger.warning(
            f"Scrape finished with error='{error}' | "
            f"returned={len(tweets)} | took={duration}s"
        )
    else:
        logger.info(
            f"Scrape finished successfully | "
            f"returned={len(tweets)} | took={duration}s"
        )

    return response
