namespace Wachta.Ingestion;

/// <summary>How this project introduces itself to the sources it reads.
///
/// Not a formality. adsb.lol answers 403 to a client that does not identify itself, and an operator
/// who cannot tell who is pulling their data has no way to ask a question before blocking. The same
/// string is used by the Python collectors in eval/feasibility, so one look at a server log shows
/// everything this project fetched, whichever layer fetched it.</summary>
public static class WachtaHttp
{
    public const string UserAgent = "wachta-research/0.1 (non-commercial portfolio project)";
}
