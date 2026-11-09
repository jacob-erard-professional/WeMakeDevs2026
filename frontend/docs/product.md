# Product and delivery plan

Help attendees make useful connections at the conference. Give them a practical schedule and explain why a talk or a person is worth their time.

## MVP

1. **Organizer creates a conference.** Import a schedule from a URL, file, or text where supported. Review parsing warnings and edit the preview before publishing. Share the attendee join link after confirmation.
2. **Attendee joins.** Open the conference link and confirm the event. Enter a name and bio and optionally add a resume, LinkedIn, and unavailable times. Make resume visibility an explicit choice with private as the proposed default.
3. **Attendee gets a plan.** Show suggested talks with reasons and conference-local times. The proposed schedule avoids overlaps and unavailable periods. Provide an empty state when no talks fit.
4. **Attendee discovers people.** Show recommendations with reasons and allow refresh as new people join. Keep discovery eligibility separate from resume visibility.
5. **Attendee requests a connection.** Show the resulting request status. Coordinate acceptance and the exact contact and resume disclosure rules with the backend team.

The demo should support this flow with keyboard navigation on web, labelled controls on native, readable text at increased scale, and explicit status and error messages.

## Delivery sequence

- **Starter:** isolated Expo project, architecture and review guidance, and synthetic recommendation preview.
- **Mock flows:** build join, profile, schedule, discovery, and connection request screens with local fixtures. Build the organizer import and review screens alongside those flows once the preview fields are agreed.
- **Integration:** confirm the FastAPI contract, replace fixtures at the data boundary, and validate one organizer-to-attendee journey against the live stack.
- **Later:** organizer insights, and recommendations for past talks based on a submitted description or transcript and the attendee's reason for interest.
