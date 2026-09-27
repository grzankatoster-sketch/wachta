using Wachta.Domain;

namespace Wachta.Ingestion;

public sealed class IngestionWorker(
    IEnumerable<IAircraftSource> sources,
    PositionDeduplicator dedup,
    MilitaryRegistry military,
    IPositionWriter writer,
    ILogger<IngestionWorker> log) : BackgroundService
{
    private readonly Lock _dedupLock = new();

    protected override Task ExecuteAsync(CancellationToken ct) =>
        Task.WhenAll(sources.Select(s => RunSourceAsync(s, ct)));

    private async Task RunSourceAsync(IAircraftSource source, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var snapshot = await source.FetchAsync(ct);
                IReadOnlyList<AircraftObservation> fresh;
                lock (_dedupLock)
                {
                    // The area endpoints do not carry dbFlags, so the flag comes from what /v2/mil told us.
                    military.Remember(snapshot.Aircraft);
                    fresh = dedup.Filter(military.Apply(snapshot.Aircraft));
                }

                var written = await writer.WriteAsync(snapshot, fresh, ct);
                log.LogInformation("{Source}: received {Received}, written {Written}", source.Id, snapshot.Aircraft.Count, written);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                log.LogWarning(ex, "{Source}: fetch failed, retrying in 30 s", source.Id);
                await Task.Delay(TimeSpan.FromSeconds(30), ct);
            }
        }
    }
}
