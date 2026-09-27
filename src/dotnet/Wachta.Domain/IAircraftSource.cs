namespace Wachta.Domain;

public interface IAircraftSource
{
    string Id { get; }
    Task<SourceSnapshot> FetchAsync(CancellationToken ct);
}
