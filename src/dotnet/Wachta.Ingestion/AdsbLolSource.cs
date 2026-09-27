using System.Security.Cryptography;
using System.Text;
using Wachta.Domain;

namespace Wachta.Ingestion;

/// <summary>Adapter: adsb.lol v2 endpoint -> common SourceSnapshot model.</summary>
public sealed class AdsbLolSource(HttpClient http, string id, Uri url, bool forceMilitary, TimeProvider clock) : IAircraftSource
{
    public string Id => id;

    public async Task<SourceSnapshot> FetchAsync(CancellationToken ct)
    {
        var body = await http.GetStringAsync(url, ct);
        var fetchedAt = clock.GetUtcNow();
        var hash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(body)));
        var parsed = AdsbV2Parser.Parse(body, fetchedAt, forceMilitary);
        return new SourceSnapshot(id, url, fetchedAt, hash, parsed.Aircraft, parsed.Contacts);
    }
}
