using System.Runtime.InteropServices;

namespace Wachta.Tests;

/// <summary>Tells whether a Docker daemon is there to talk to, without asking Docker.
///
/// Testcontainers answers the same question by opening a connection and throwing a page of stack
/// trace when it fails. On a machine without Docker that turns eighteen honest "not run here" into
/// eighteen red failures, which hides the ones that would matter. Looking for the socket is cheap,
/// silent, and enough.</summary>
public static class DockerAvailable
{
    private static readonly Lazy<string?> Missing = new(Detect);

    /// <summary>Null when Docker can be reached, otherwise the reason to print in the skip.</summary>
    public static string? Reason => Missing.Value;

    public static bool Yes => Missing.Value is null;

    private static string? Detect()
    {
        if (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("DOCKER_HOST")))
        {
            return null;
        }

        var endpoint = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
            ? @"\\.\pipe\docker_engine"
            : "/var/run/docker.sock";

        return File.Exists(endpoint) || Directory.Exists(endpoint)
            ? null
            : $"brak Dockera ({endpoint} nie istnieje) - test wymaga bazy w kontenerze";
    }
}

/// <summary>A fact that needs a real PostgreSQL in a container.</summary>
public sealed class DockerFactAttribute : FactAttribute
{
    public DockerFactAttribute() => Skip = DockerAvailable.Reason;
}

/// <summary>A theory that needs a real PostgreSQL in a container.</summary>
public sealed class DockerTheoryAttribute : TheoryAttribute
{
    public DockerTheoryAttribute() => Skip = DockerAvailable.Reason;
}
